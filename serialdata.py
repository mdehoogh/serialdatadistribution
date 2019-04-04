"""
MDH@02APR2019:
- SerialByteDispatcher reads the serial data from an associated serial port
  and informs ByteReaders about it

 """

# wrapping reading serial data in a class descending from a Thread
# so we can keep interfacing with this program while serial data is read and relayed
import _thread
import serial
import queue
import sys
import time

# ByteReceiver is the parent class of all ByteReceiver
class ByteReader:
	# exposes a method that will return the number of bytes received so far
	def __init__(self,_queue=False):
		self.serialDataDispatcher=None
		self.numberOfReadBytes=0 # keep track of the number of bytes collected so far
		# if in an interactive session we will queue whatever we retrieve
		self.numberOfWrittenBytes=0
		if _queue:
			self.readBytesQueue=queue.Queue()
		else:
			self.readBytesQueue=None

	def __iter__(self): # if it has a queue to iterate and a serial data dispatcher return self, otherwise None
		return (self,None)[self.serialDataDispatcher is None or self.readBytesQueue is None]
	# NOTE the iteration will never end if we do not generate StopIteration
	def __next__(self):
		# if no associated dispatcher anymore or the dispatcher is no longer running
		if self.serialDataDispatcher is None or not self.serialDataDispatcher.isRunning():
			raise StopIteration
		# only when there's nothing left to read, return something
		if self.getNumberOfBytesToRead()==0:
			try:
				# there's no need to block and wait at all here, simply return None if there's no data!!!
				readBytes=self.readBytesQueue.get_nowait()
				self.numberOfWrittenBytes+=len(readBytes)
				return readBytes
			except:
				pass
		return None
	def getNumberOfReadBytes(self):
		return self.numberOfReadBytes
	# setSerialDataDispatcher() raises an exception if the input is invalid, otherwise it returns the current serial data dispatcher (the one that is replaced)
	def setSerialDataDispatcher(self,_serialDataDispatcher):
		if _serialDataDispatcher is not None and not isinstance(_serialDataDispatcher,SerialDataDispatcher):
			raise Exception("Not a serial data dispatcher.")
		currentSerialDataDispatcher=self.serialDataDispatcher
		self.serialDataDispatcher=_serialDataDispatcher
		self.numberOfBytesRead=0 # this is essential because NO bytes have been read so far from the given serial data dispatcher, of course it could be the same dispatcher so this is like a reset!!!
		return currentSerialDataDispatcher
	def getSerialDataDispatcher(self):
		return self.serialDataDispatcher
	# call __read() with the number of bytes to read which is at most self.numberOfUnretrievedBytes
	def __read(self,_numberOfBytesToRead=0):
		if not isinstance(_numberOfBytesToRead,int) or _numberOfBytesToRead<0:
			raise Exception("Number of bytes to read invalid.")
		if not self.serialDataDispatcher:
			raise Exception("No associated serial data dispatcher.")
		try:
			(firstReadByteIndex,readBytes)=self.serialDataDispatcher.readBytes(self,_numberOfBytesToRead)
			self.numberOfReadBytes+=len(readBytes)
			return readBytes
		except:
			pass
		return None
	# update() is called by self.serialDataDispatcher when new bytes were stored, you should override it in a subclass to prevent printing
	def update(self,_numberOfStoredBytes):
		# here's a little issue in that _numberOfStoredBytes is what the serial data dispatcher has read, but this might not be the maximum that could be retrieved
		# therefore we simply read everything (i.e. )
		try:
			bytesRead=self.__read()
			if self.readBytesQueue:
				self.readBytesQueue.put_nowait(bytesRead)
			else:
				print("Read by byte reader '"+self.name+"': '"+str(self.read())+"'.")
		except:
			pass
	def getNumberOfBytesToRead(self):
		return self.serialDataDispatcher.getNumberOfStoredBytes()-self.numberOfReadBytes
	def write(self,_bytes): # service
		if self.serialDataDispatcher:
			return self.serialDataDispatcher.write(_bytes)
		return 0
	# service methods
	def report(self):
		if self.serialDataDispatcher:
			self.serialDataDispatcher.printReported()
	def start(self):
		if self.serialDataDispatcher:
			return self.serialDataDispatcher.start()
		return False
	def stop(self):
		# NOTE stop() doesn't actually stop the dispatcher, you would need to do that through the serial data dispatcher
		if self.serialDataDispatcher:
			self.serialDataDispatcher.removeByteReader(self)
		return self.serialDataDispatcher is None
	def __str__(self):
		status="Read="+str(self.numberOfReadBytes)+" - left to read="+str(self.getNumberOfBytesToRead())
		if self.readBytesQueue:
			status+=" - left to write="+str(self.numberOfReadBytes-self.numberOfWrittenBytes)
		return status
	def __repr__(self):
		return self.__str__()

class Reporter:
	def report(self,_report):
		print(_report)

# SerialDataDispatcher keeps as many bytes as it needs
class SerialDataDispatcher:

	# if we have a reporter, we report it directly to the reporter, otherwise we queue if for pulling instead of pushing
	def __report(self,_report):
		try:
			self.reported.put_nowait(_report)
		except:
			pass
		try:
			self.reporter.report(_report)
		except:
			pass

	def __init__(self,_serialInputDevice,_queuereported=True):
		if not isinstance(_serialInputDevice,serial.Serial):
			raise Exception("No (proper) serial input device specified.")
		if not _serialInputDevice.isOpen:
			raise Exception("Serial input device '"+_serialInputDevice.name+"' is not open.")
		self.paused=False
		self.running=False
		self.numberOfReadBytes=0 # the total number of bytes read
		self.numberOfStoredBytes=0 # the index of the last byte stored in self.retrievableBytes
		self.numberOfUnstoredBytes=0 # the number of bytes we failed to store somehow (perhaps retrievableBytes is full?????)
		self.numberOfAnonymouslyReadBytes=0 # keep track of the number of bytes anonymously read so far
		self.retrievableBytes=bytearray() # all bytes currently available 
		self.byteReaders={} # the parties interested in reading the packets registered by some unique key (name)
		if _queuereported: # remembers everything reported
			self.reported=queue.Queue()
		else:
			self.reported=None
		self.serialInputDevice=_serialInputDevice
		self.name=self.serialInputDevice.name # even if we kill the reference

	def __del__(self):
		# ascertain to be closed!!
		self.stop()
	
	def __process_bytes(self,_bytes):
		numberOfBytesToStore=len(_bytes)
		if numberOfBytesToStore>0:
			self.numberOfReadBytes+=numberOfBytesToStore # update the total number of read bytes
			# try to append ALL bytes and keep track of the number of bytes yet to be stored
			l=len(self.retrievableBytes)
			try:
				# append all the bytes read
				for _byte in _bytes:
					self.retrievableBytes.append(_byte)
			except:
				pass
			stored=len(self.retrievableBytes)-l # number of bytes actually stored (of course, in storing the bytes no one should dispose bytes from it)
			self.numberOfStoredBytes+=stored
			unstored=numberOfBytesToStore-stored
			if unstored:
				self.numberOfUnstoredBytes+=unstored
				self.__report("ERROR: Failed to store "+str(unstored)+" bytes.")

			# after storing all byte we're reading to inform the byte retrievers
			if stored:
				for byteReader in self.byteReaders.values():
					if byteReader.getSerialDataDispatcher()==self:
						try:
							byteReader.update(stored)
						except Exception as ex:
							self.__report("ERROR: '"+str(ex)+"' telling byte reader '"+str(byteReader)+" to update.")

	def __updateRetrievableBytes(self):
		if len(self.byteReaders) or self.numberOfAnonymouslyReadBytes:
			lock=_thread.allocate_lock()
			with lock:
				numberOfDisposedBytes=self.getNumberOfDisposedBytes()
				if len(self.byteReaders):
					smallestNumberOfAdditionalBytesRetrieved=0
					for byteReader in self.byteReaders.values():
						numberOfAdditionalBytesRetrieved=byteReader.getNumberOfReadBytes()-numberOfDisposedBytes
						if numberOfAdditionalBytesRetrieved<=0: # we're done!
							return
						# now if the number of supposedly retrieved bytes does not exceed 
						if smallestNumberOfAdditionalBytesRetrieved==0 or numberOfAdditionalBytesRetrieved<smallestNumberOfAdditionalBytesRetrieved:
							smallestNumberOfAdditionalBytesRetrieved=numberOfAdditionalBytesRetrieved
				else: # we'll be disposing all the anonymously read bytes!!!
					smallestNumberOfAdditionalBytesRetrieved=self.numberOfAnonymouslyReadBytes-numberOfDisposedBytes
				# determine the smallest number of bytes retrieved by all 
				# if we have additional bytes retrieved, let's remove them from the bytearray
				if smallestNumberOfAdditionalBytesRetrieved>0:
					del self.retrievableBytes[:smallestNumberOfAdditionalBytesRetrieved]

	def __run(self,_sleep):
		if self.serialInputDevice is not None:
			self.__report("'"+self.name+"' will start running...")
			self.paused=False
			self.running=True
			# keep reading as long as the serial input device is (still) open
			while self.running:
				if self.serialInputDevice.out_waiting:
					self.serialInputDevice.flush() # write everything that can be written
				# when paused, assume nothing to read...
				numberOfBytesToRead=(self.serialInputDevice.in_waiting,0)[self.paused]
				if numberOfBytesToRead:
					self.__process_bytes(self.serialInputDevice.read(size=numberOfBytesToRead))
				else: # got some time to tidy up...
					self.__updateRetrievableBytes()
				"""
					self.__report("Reading "+str(numberOfBytesToRead)+" bytes from '"+self.name+"'...")
				else:
					self.__report("Nothing to read from '"+self.name+"'...")
				"""
				if _sleep>0:
					time.sleep(_sleep)
			self.__report("'"+self.name+"' finished running...")
			self.__close() # as soon as the loop ends close the serial port connection as well...

	def __close(self):
		# ascertain to close only once
		if self.serialInputDevice:
			try:
				self.serialInputDevice.flushInput() # TODO should we do this?????
				self.serialInputDevice.flushOutput() # TODO should we do this?????
				self.serialInputDevice.close()
				self.__report("Connection to '"+self.name+"' closed.")
			except Exception as ex:
				self.__report("ERROR: '"+str(ex)+"' closing the connection to '"+self.name+"'.")
			finally: # ascertain to remove the reference
				self.serialInputDevice=None
		
	def __str__(self):
		# when working let's also show the first and last index we have in store
		return self.name+((' FINISHED',' IDLE')[self.isRunnable()],' WORKING ['+str(self.getNumberOfDisposedBytes())+","+str(self.getNumberOfStoredBytes()-1)+']')[self.isRunning()] # appending - (done), + (runnable), * (running)
	
	def __repr__(self):
		return self.__str__()
		
	# 'PUBLIC'
	# as a convenience we allow reading a certain number of bytes anonymously
	def read(self,_numberOfBytesToRead=0,_firstByteToRead=None):
		if _firstByteToRead is not None and not isinstance(_firstByteToRead,int):
			self.__report("ERROR: Invalid first byte to read anonymously.")
			return None
		if not isinstance(_numberOfBytesToRead,int) or _numberOfBytesToRead<0:
			self.__report("ERROR: Invalid number of bytes to read anonymously.")
			return None
		# if no first byte to read was specified start with the number of anonymously read bytes
		if _firstByteToRead is None:
			_firstByteToRead=self.numberOfAnonymouslyReadBytes
		# the actual first byte
		firstByteToRead=_firstByteToRead-self.getNumberOfDisposedBytes()
		if firstByteToRead<0:
			self.__report("First byte to read anonymously ("+str(firstByteToRead)+") not available (any more).")
			return None
		if firstByteToRead>=len(self.retrievableBytes):
			self.__report("First byte to read anonymously ("+str(firstByteToRead)+">="+str(len(self.retrievableBytes))+") not available yet.")
			return None
		if _numberOfBytesToRead: # a fixed amount to read specified...
			readBytes=self.retrievableBytes[firstByteToRead:firstByteToRead+_numberOfBytesToRead]
		else:
			readBytes=self.retrievableBytes[firstByteToRead:]
		# remember what we're returning (skipping firstByteToRead bytes at the start that might get disposed!!!)
		self.numberOfAnonymouslyReadBytes+=(firstByteToRead+len(readBytes))
		return readBytes

	def readBytes(self,_byteReader,_numberOfBytesToRead):
		if not isinstance(_byteReader,ByteReader):
			raise Exception("No byte reader defined.")
		if isinstance(_numberOfBytesToRead,int) and _numberOfBytesToRead>=0:
			if _byteReader.getSerialDataDispatcher()==self:
				# the index of the first retrievable bytes equals the number of retrieved bytes minus the number of disposed bytes
				firstByteToRead=_byteReader.getNumberOfReadBytes()-self.getNumberOfDisposedBytes()
				if _numberOfBytesToRead:
					return (firstByteToRead,self.retrievableBytes[firstByteToRead:firstByteToRead+_numberOfBytesToRead])
				return (firstByteToRead,self.retrievableBytes[firstByteToRead:])
			self.report("Requesting byte reader '"+str(_byteReader)+"' not associated with the serial data dispatcher of '"+self.name+"'.")
		return None

	def isRunning(self):
		return self.running

	def isRunnable(self):
		# considered runnable if it is not currently running and can be run...
		return not self.running and self.serialInputDevice is not None

	def write(self,_bytes):
		if isinstance(_bytes,bytes):
			if self.serialInputDevice is not None and self.serialInputDevice.isOpen:
				return self.serialInputDevice.write(_bytes)
		return 0
		
	def getNumberOfReadBytes(self):
		return self.numberOfReadBytes

	def getNumberOfStoredBytes(self):
		return self.numberOfStoredBytes

	def getNumberOfRetrievableBytes(self):
		return len(self.retrievableBytes)

	def getNumberOfDisposedBytes(self):
		return self.getNumberOfStoredBytes()-self.getNumberOfRetrievableBytes()

	# start() and stop()
	def start(self,_sleep=0.0):
		if not isinstance(_sleep,(int,float)) or _sleep<0:
			self.__report("Sleep time invalid.")
			return None
		# can't run twice!!!
		if self.serialInputDevice is None:
			self.__report("Can't start '"+self.name+"' again.")
			return None
		if self.running:
			self.__report("Can't start '"+self.name+"': it has already started.")
		else: # start a new thread that executes __run
			_thread.start_new_thread(self.__run,(_sleep,))
		return self
	def stop(self):
		if self.serialInputDevice is None:
			self.__report("Can't stop '"+self.name+"' again.")
			return False
		if not self.running:
			self.__report("Can't stop '"+self.name+"' it has already stopped.")
		else:
			self.running=False
		return not self.running
	def pause(self):
		if self.running:
			self.paused=True
		else:
			self.__report("Can't pause '"+self.name+"': not currently running!")
		return self.paused
	def resume(self):
		if self.running:
			self.paused=False
		else:
			self.__report("Can't resume '"+self.name+"': not currently running!")
		return not self.paused

	def setReporter(self,_reporter):
		if _reporter is not None:
			if not hasattr(_reporter,'report') or type(_reporter.report)!="<class 'method'>":
				raise Exception("Reporter does not have a report() method.")
		self.reporter=_reporter
		return self

	def printReported(self):
		if self.reported:
			while not self.reported.empty():
				print(self.reported.get_nowait())
		else:
			print("ERROR: Wasn't told to remember the reports.")

	# byteReaders support
	def removeByteReaderWithName(self,_byteReaderName):
		if not isinstance(_byteReaderName,str):
			raise Exception("Undefined or invalid byte reader name!")
		try:
			del self.byteReaders[_byteReaderName] # might fail if it wasn't present to start with
		except:
			self.__report("ERROR: Failed to remove byte reader '"+_byteReaderName+"' from the list of byte readers of the serial data dispatcher of '"+self.name+"'.")
		result=not _byteReaderName in self.byteReaders # if not present (anymore), remove its reference to me
		if result:
			byteReader.setSerialDataDispatcher(None) # always succeeds
		return result
	def removeByteReader(self,_byteReader):
		for (byteReaderName,byteReader) in self.byteReaders.items():
			if byteReader==_byteReader:
				return removeByteReaderWithName(byteReaderName)
		return False
	def addByteReader(self,_byteReader,_byteReaderName=''):
		if not isinstance(_byteReaderName,str) or not isinstance(_byteReader,ByteReader):
			raise Exception("Undefined/invalid byte reader or byte reader name!")
		# needs to be a ByteReader to start with
		result=False
		if not _byteReaderName in self.byteReaders: # not currently registered (under that name)
			try:
				self.byteReaders[_byteReaderName]=_byteReader
				_byteReader.setSerialDataDispatcher(self) # won't raise an exception because the input is not invalid
				result=True
			except:
				self.__report("ERROR: '"+str(ex)+"' in adding byte reader '"+_byteReaderName+"' to the list of byte readers of the serial data dispatcher of '"+self.name+"'.")
		elif self.byteReaders[_byteReaderName]==_byteReader: # already have it!!!
			result=True
		else:
			self.__report("ERROR: Another byte reader called '"+_byteReaderName+"' already registered with the serial data dispatcher of '"+self.name+"'.")
		return result

	def getByteReader(self,_byteReaderName=''):
		if isinstance(_byteReaderName,str):
			# add the anonymous byte reader (with empty name) JIT 
			if len(_byteReaderName)==0 and not '' in self.byteReaders:
				if addByteReader(ByteReader(True)):
					self.start()
				else:
					self.__report("ERROR: Failed to add the default byte reader!")
			if _byteReaderName in self.byteReaders:
				return self.byteReaders[_byteReaderName]
		return None
	def getByteReaderNames(self):
		return self.byteReaders.keys()

# keep a dictionary of serial data dispatchers (by serial port name)
serialDataDispatchers={}

# functions for getting serial device parameter values
def getBaudrate(_baudrate=None):
	BAUDRATES=(50,75,110,134,150,200,300,600,1200,1800,2400,4800,9600,19200,38400,57600,115200,230400,460800,500000,576000,921600,1000000,1152000,1500000,2000000,2500000,3000000,3500000,4000000)
	try:
		if _baudrate is None:
			print("Available baudrates: "+str(BAUDRATES)+".")
			baudrate=int(input("What baudrate to use (default: 9600)? "))
		else:
			baudrate=int(_baudrate)
		if baudrate in BAUDRATES:
			return baudrate
	except:
		pass
	print("WARNING: No or invalid baudrate specified: the default will be used!")
	return 9600
def getBytesize(_bytesize=None):
	BYTESIZES=(serial.FIVEBITS,serial.SIXBITS,serial.SEVENBITS,serial.EIGHTBITS)
	try:
		if _bytesize is None:
			print("Available byte sizes: "+str(BYTESIZES)+".")
			bytesize=int(input("What byte size to use (default: "+str(serial.EIGHTBITS)+")? "))
		else:
			bytesize=int(_bytesize)
		if bytesize in BYTESIZES:
			return bytesize
	except:
		pass
	print("WARNING: No or invalid bytesize specified: the default will be used!")
	return serial.EIGHTBITS
def getParity(_partity=None):
	PARITIES=(serial.PARITY_NONE,serial.PARITY_EVEN,serial.PARITY_ODD,serial.PARITY_MARK,serial.PARITY_SPACE)
	try:
		if _parity is None:
			print("Available parities: "+str(PARITIES)+".")
			parity=int(input("What parity to use (default: "+str(serial.PARITY_NONE)+")? "))
		else:
			parity=int(_parity)
		if parity in PARITIES:
			return parity
	except:
		pass
	print("WARNING: No or invalid parity specified: the default will be used!")
	return serial.PARITY_NONE
def getStopbits(_stopbits=None):
	STOPBITS=(serial.STOPBITS_ONE,serial.STOPBITS_ONE_POINT_FIVE,serial.STOPBITS_TWO)
	try:
		if _stopbits is None:
			print("Available number of stop bits: "+str(STOPBITS)+".")
			stopbits=int(input("What number of stop bits to use (default: "+str(serial.STOPBITS_ONE)+")? "))
		else:
			stopbits=int(_stopbits)
		if stopbits in STOPBITS:
			return stopbits
	except:
		pass
	print("WARNING: No or invalid stopbits specified: the default will be used!")
	return serial.STOPBITS_ONE
def getTimeout(_timeout=None):
	try:
		if _timeout is None:
			timeout=float(input("What timeout (in seconds) to use (default: none)? "))
		else:
			timeout=float(_timeout)
		if timeout>0:
			return timeout
	except:
		pass
	print("WARNING: No or an invalid timeout specified: no timeout will be used.")
	return None
def getXonxoff(_xonxoff=None):
	if _xonxoff is None:
		return input("Use xon - xoff (default: False)? ") in ('Y','y')
	return (False,True)[_xonxoff in ('Y','y')]
def getRtscts(_rtscts=None):
	if _rtscts is None:
		return input("Use rts - cts (default: False)? ") in ('Y','y')
	return (False,True)[_rtscts in ('Y','y')]
def getWrite_timeout(_write_timeout=None):
	try:
		if _write_timeout is None:
			write_timeout=float(input("What write timeout (in seconds) to use (default: none)? "))
		else:
			write_timeout=float(_write_timeout)
		if write_timeout>0:
			return write_timeout
	except:
		pass
	print("WARNING: No or an invalid write timeout specified: no write timeout will be used.")
	return None
def getDsrdtr(_dsrdtr=None):
	if _dsrdtr is None:
		return input("Use dsr - dtr (default: False)? ") in ('Y','y')
	return (False,True)[_dsrdtr in ('Y','y')]
def getInter_byte_timeout(_inter_byte_timeout=None):
	try:
		if _inter_byte_timeout is None:
			inter_byte_timeout=float(input("What inter-character timeout (in seconds) to use (default: none)? "))
		else:
			inter_byte_timeout=float(_inter_byte_timeout)
		if inter_byte_timeout>0:
			return inter_byte_timeout
	except:
		pass
	print("WARNING: No or an invalid inter-character timeout specified: no inter-character timeout will be used.")
	return None
def getExclusive(_exclusive=None):
	if _exclusive is None:
		return input("Use exclusive access mode (POSIX only) (default: False)? ") in ('Y','y')
	return (False,True)[_exclusive in ('Y','y')]
	
def addSerial(_serial,_report):
	if _serial is None:
		raise Exception("No serial input device specified.")
	global serialDataDispatchers
	if not _serial.port in serialDataDispatchers or not serialDataDispatchers[_serial.port].isRunning():
		try:
			serialDataDispatchers[_serial.port]=SerialDataDispatcher(_serial,_report)
		except Exception as ex:
			print("ERROR: '"+str(ex)+"' instantiating the reader to read serial data from port '"+_serial.port+"'.")
	if _serial.port in serialDataDispatchers:
		return serialDataDispatchers[_serial.port]
	return None
def getSerialDataDispatcher(inputDeviceName=None,report=True):
	# is there a default device?
	if not isinstance(inputDeviceName,str):
		inputDeviceName=None
		# show a list of serial input devices to choose from (in groups of 9)
		import serial.tools.list_ports
		serialPortInfos=serial.tools.list_ports.comports()
		# show serial ports in groups of at most 9 options
		if serialPortInfos is not None:
			print("Number of serial ports: "+str(len(serialPortInfos))+".")
			serialPortInfoPages=1+(len(serialPortInfos)-1)//9
		else:
			serialPortInfoPages=0
		if serialPortInfoPages>0:
			serialPortInfoPage=1
			while serialPortInfoPage<=serialPortInfoPages:
				print("Serial ports (page "+str(serialPortInfoPage)+" of "+str(serialPortInfoPages)+")")
				serialPortInfoIndex=9*serialPortInfoPage-10 # one less than the index into the list
				for optionIndex in range(1,10):
					if serialPortInfoIndex+optionIndex>=len(serialPortInfos):
						break
					serialPortInfo=serialPortInfos[serialPortInfoIndex+optionIndex]
					print(str(optionIndex)+". "+str(serialPortInfo.device))
				while 1:
					selectedOption=input("What is the number of the serial port to use? ")
					# if no option was selected go and show the next one
					if len(selectedOption)==0:
						break
					try:
						selectedOptionIndex=int(selectedOption)
						if selectedOptionIndex>0 and selectedOptionIndex+serialPortInfoIndex<=len(serialPortInfos):
							inputDeviceName=serialPortInfos[selectedOptionIndex+serialPortInfoIndex].device
							break
					except Exception as ex:
						print("ERROR: '"+str(ex)+"' processing selected option '"+selectedOption+"'.")
				if inputDeviceName is not None:
					break
				serialPortInfoPage+=1
		else:
			print("No serial devices available.")
	if inputDeviceName is None:
		return None
	return addSerial(serial.Serial(port=inputDeviceName,baudrate=getBaudrate(),bytesize=getBytesize(),parity=getParity(),stopbits=getStopbits(),timeout=getTimeout(),xonxoff=getXonxoff(),rtscts=getRtscts(),write_timeout=getWrite_timeout(),dsrdtr=getDsrdtr(),inter_byte_timeout=getInter_byte_timeout(),exclusive=getExclusive()),report)

def new():
	return getSerialDataDispatcher(None,input("Do you want to use a default reporter? ") in ('Y','y'))

# if ran from the command line expecting all required parameters as command line arguments
def main(args):
	if len(args):
		inputDeviceName=args[0]
		if len(inputDeviceName)>0:
			map={'baudrate':'','bytesize':'','parity':'','stopbits':'','timeout':'','xonxoff':'','rtscts':'','write_timeout':'','dsrdtr':'','inter_byte_timeout':'','exclusive':''}
			for argIndex in range(1,len(args)):
				try:
					equalPos=args[argIndex].index('=')
					map[args[argIndex][:equalPos]]=args[argIndex][equalPos+1:]
				except:
					pass
			serialDataDispatcher=addSerial(serial.Serial(port=inputDeviceName,baudrate=getBaudrate(map['baudrate']),bytesize=getBytesize(map['bytesize']),parity=getParity(map['parity']),stopbits=getStopbits(map['stopbits']),timeout=getTimeout(map['timeout']),xonxoff=getXonxoff(map['xonxoff']),rtscts=getRtscts(map['rtscts']),write_timeout=getWrite_timeout(map['write_timeout']),dsrdtr=getDsrdtr(map['dsrdtr']),inter_byte_timeout=getInter_byte_timeout(map['inter_byte_timeout']),exclusive=getExclusive(map['exclusive'])),True)
			if serialDataDispatcher is not None:
				if serialDataDispatcher.write(b'\r\n'):
					if serialDataDispatcher.start():
						while True:
							bytesRead=serialDataDispatcher.read()
							if bytesRead is None: # something the matter????
								serialDataDispatcher.printReported()
							else:
								print("Read: '"+str(bytesRead)+"'.")
							time.sleep(0.1) # sleep a little while
						print("Serial data dispatcher not running anymore!")
					else:
						print("ERROR: Failed to start the serial data dispatcher.")
					# TODO alternatively we could now read anonymously (i.e. without a byte reader!!!)
					""" replacing:
					byteReader=serialDataDispatcher.getByteReader() # will now create the anonymous byte reader JIT and start the dispatcher!!
					if byteReader is not None:
						while byteReader.readBytesQueue:
							while not byteReader.readBytesQueue.empty():
								print(byteReader.readBytesQueue.get_nowait())
							time.sleep(1)
						print("No read bytes queue to pull!")
					else:
						print("ERROR: No default byte reader available!")
					"""
				else:
					print("ERROR: Failed to write to the serial input device.")
			else:
				print("ERROR: Failed to create a serial data dispatcher.")
		else:
			print("No serial input device specified.")
	else:
		print("Need at least the name of the serial input device! Any parameters should be presented on the command-line in the format <name>=<value> e.g. baudrate=9600!")		

def test():
	# try to get a dispatcher that starts immediately
	serialDataDispatcher=getSerialDataDispatcher(None,True)
	if serialDataDispatcher is not None:
		serialDataDispatcher.start()
		serialDataDispatcher.printReported()
		if serialDataDispatcher.isRunning():
			print("Serial data dispatcher to serial port '"+serialDataDispatcher.serialInputDevice.name+"' up and running...")
		else:
			print("WARNING: Serial data dispatcher to serial port '"+serialDataDispatcher.serialInputDevice.name+"'  NOT  up and running...")
	else:
		print("ERROR: Failed to create a serial data dispatcher.")

if __name__=='__main__':
	main(sys.argv[1:])
else:
	print("Call serialdata.new() to obtain a serial data dispatcher; call getByteReader() on the serial data dispatcher to obtain the default byte reader; write bytes calling write() on either.")

	
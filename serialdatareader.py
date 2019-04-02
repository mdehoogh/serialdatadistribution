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

# ByteReceiver is the parent class of all ByteReceiver
class ByteRetriever:
	# exposes a method that will return the number of bytes received so far
	def __init__(self,_name='anonymous'):
		self.name=_name
		self.__numberOfRetrievedBytes=0 # keep track of the number of bytes collected so far
	def getNumberOfRetrievedBytes(self):
		return self.__numberOfRetrievedBytes
	# updateRetrievedBytes is called
	def updateRetrievedBytes(self,_serialDataReader):
		# just get all the bytes I haven't got yet
		(firstRetrievedByteIndex,retrievedBytes)=_serialDataReader.retrieveBytes(self)
		if retrievedBytes is not None:
			self.__numberOfRetrievedBytes+=len(retrievedBytes)
			print("Retrieved by byte retriever '"+self.name+"': '"+str(retrievedBytes)+"' (starting at index "+str(firstRetrievedByteIndex)+", now totalling "+str(self.__numberOfRetrievedBytes)+" bytes).")
	def __str__(self):
		return str(self.name)
	def __repr__(self):
		return self.__str__()

class Reporter:
	def report(self,_report):
		print(_report)

# SerialDataReader keeps as many bytes as it needs
class SerialDataReader:

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
		self.running=False
		self.sleep=0.0 # by default do not sleep in the __run method
		self.numberOfReadBytes=0 # the total number of bytes read
		self.numberOfStoredBytes=0 # the index of the last byte stored in self.retrievableBytes
		self.numberOfUnstoredBytes=0 # the number of bytes we failed to store somehow (perhaps retrievableBytes is full?????)
		self.retrievableBytes=bytearray() # all bytes currently available 
		self.byteRetrievers=[] # the parties interested in reading the packets...
		self.byteRetrieverCount=0
		if _queuereported: # remembers everything reported
			self.reported=queue.Queue()
		else:
			self.reported=None
		self.serialInputDevice=_serialInputDevice
		self.name=self.serialInputDevice.name # even if we kill the reference

	def __del__(self):
		# ascertain to be closed!!
		self.stop()
	
	def __getByteRetrieverIndex(self,_byteRetriever):
		for byteRetrieverIndex in range(0,len(self.byteRetrievers)):
			if self.byteRetrievers[byteRetrieverIndex]==_byteRetriever:
				return byteRetrieverIndex
		return -1

	def __process_bytes(self,_bytes):
		byteCount=len(_bytes)
		if byteCount>0:
			self.numberOfReadBytes+=byteCount # update the total number of read bytes
			# try to append ALL bytes and keep track of the number of bytes yet to be stored
			try:
				# append all the bytes read
				for _byte in _bytes:
					self.retrievableBytes.append(_byte)
					byteCount-=1
			except:
				pass
			if byteCount>0:
				self.numberOfUnstoredBytes+=bytecount
				self.__report("Failed to store "+str(bytecount)+" serial bytes.")

			# after storing all byte we're reading to inform the byte retrievers
			for byteRetriever in self.byteRetrievers:
				try:
					byteRetriever.updateRetrievedBytes(self)
				except Exception as ex:
					self.__report("ERROR: '"+str(ex)+"' informing a byte retriever.")

	def __updateRetrievableBytes(self):
		if len(self.byteRetrievers):
			lock=_thread.allocate_lock()
			with lock:
				numberOfDisposedBytes=self.numberOfStoredBytes-len(self.retrievableBytes)
				# determine the smallest number of bytes retrieved by all 
				smallestNumberOfAdditionalBytesRetrieved=0
				for byteRetriever in self.byteRetrievers:
					numberOfAdditionalBytesRetrieved=byteRetriever.getNumberOfRetrievedBytes()-numberOfDisposedBytes
					if numberOfAdditionalBytesRetrieved<=0: # we're done!
						return
					# now if the number of supposedly retrieved bytes does not exceed 
					if smallestNumberOfAdditionalBytesRetrieved==0 or numberOfAdditionalBytesRetrieved<smallestNumberOfAdditionalBytesRetrieved:
						smallestNumberOfAdditionalBytesRetrieved=numberOfAdditionalBytesRetrieved
				# if we have additional bytes retrieved, let's remove them from the bytearray
				if smallestNumberOfAdditionalBytesRetrieved>0:
					del self.retrievableBytes[:smallestNumberOfAdditionalBytesRetrieved]

	def __run(self,_sleep):
		if self.serialInputDevice is not None:
			self.__report("'"+self.name+"' will start running...")
			self.running=True
			# keep reading as long as the serial input device is (still) open
			while self.running:
				if self.serialInputDevice.out_waiting:
					self.serialInputDevice.flush() # write everything that can be written
				numberOfBytesToRead=self.serialInputDevice.in_waiting
				if numberOfBytesToRead:
					self.__process_bytes(self.serialInputDevice.read(size=numberOfBytesToRead))
					# TODO should we try to find out whether we can remove bytes now????
					self.__updateRetrievableBytes()
				"""
					self.__report("Reading "+str(numberOfBytesToRead)+" bytes from '"+self.name+"'...")
				else:
					self.__report("Nothing to read from '"+self.name+"'...")
				"""
				if self.sleep>0:
					time.sleep(self.sleep)
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
	def retrieveBytes(self,_byteRetriever):
		# TODO we need to be careful here!!!
		if self.__getByteRetrieverIndex(_byteRetriever)>=0:
			# the index of the first retrievable bytes equals the number of retrieved bytes minus the number of disposed bytes
			firstRetrievableByte=_byteRetriever.getNumberOfRetrievedBytes()-self.getNumberOfDisposedBytes()
			# NOTE that numberOfDisposedBytes should never exceed numberOfRetrievedBytes
			if firstRetrievableByte>=0:
				return (firstRetrievableByte,self.retrievableBytes[firstRetrievableByte:])
		else:
			self.__report("Unregistered byte retriever.")
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
		
	def getNumberOfReadBytes():
		return self.numberOfReadBytes

	def getNumberOfStoredBytes():
		return self.numberOfStoredBytes

	def getNumberOfRetrievableBytes(self):
		return len(self.retrievableBytes)

	def getNumberOfDisposedBytes(self):
		return self.getNumberOfStoredBytes()-self.getNumberOfRetrievableBytes()

	# makes more sense to have a stop() instead of a close()
	def start(self,_sleep=0.0):
		if isinstance(_sleep,(int,float)):
			self.sleep=_sleep
		# can't run twice!!!
		if self.serialInputDevice is None:
			self.__report("Can't start '"+self.name+"' again.")
		elif self.running:
			self.__report("Can't start '"+self.name+"': it has already started.")
		else: # start a new thread that executes __run
			_thread.start_new_thread(self.__run,(_sleep,))

	def stop(self):
		if self.serialInputDevice is None:
			self.__report("Can't stop '"+self.name+"' again.")
		elif not self.running:
			self.__report("Can't stop '"+self.name+"' it has already stopped.")
		else:
			self.running=False
		
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

	def deleteByteRetriever(self,_byteRetriever):
		try:
			if isinstance(_byteRetriever,ByteRetriever):
				byteRetrieverIndex=self.__getByteRetrieverIndex(_byteRetriever)
				if byteRetrieverIndex>=0:
					del self.byteRetrievers[byteRetrieverIndex]
					return True
		except:
			pass
		return False			
	def addByteRetriever(self,_byteRetriever):
		try:
			if isinstance(_byteRetriever,ByteRetriever):
				if self.__getByteRetrieverIndex(_byteRetriever)>=0:
					return True
				self.byteRetrievers.append(_byteRetriever)
				return True
		except:
			pass
		return False

# keep a dictionary of serial data distributors (by name)
serialDataReaders={}

# functions for getting serial device parameter values
def getBaudrate():
	BAUDRATES=(50,75,110,134,150,200,300,600,1200,1800,2400,4800,9600,19200,38400,57600,115200,230400,460800,500000,576000,921600,1000000,1152000,1500000,2000000,2500000,3000000,3500000,4000000)
	try:
		print("Available baudrates: "+str(BAUDRATES)+".")
		baudrate=int(input("What baudrate to use (default: 9600)? "))
		if baudrate in BAUDRATES:
			return baudrate
	except:
		pass
	print("WARNING: No or invalid baudrate specified: the default will be used!")
	return 9600
def getBytesize():
	BYTESIZES=(serial.FIVEBITS,serial.SIXBITS,serial.SEVENBITS,serial.EIGHTBITS)
	try:
		print("Available byte sizes: "+str(BYTESIZES)+".")
		bytesize=int(input("What byte size to use (default: "+str(serial.EIGHTBITS)+")? "))
		if bytesize in BYTESIZES:
			return bytesize
	except:
		pass
	print("WARNING: No or invalid bytesize specified: the default will be used!")
	return serial.EIGHTBITS
def getParity():
	PARITIES=(serial.PARITY_NONE,serial.PARITY_EVEN,serial.PARITY_ODD,serial.PARITY_MARK,serial.PARITY_SPACE)
	try:
		print("Available parities: "+str(PARITIES)+".")
		parity=int(input("What parity to use (default: "+str(serial.PARITY_NONE)+")? "))
		if parity in PARITIES:
			return parity
	except:
		pass
	print("WARNING: No or invalid parity specified: the default will be used!")
	return serial.PARITY_NONE
def getStopbits():
	STOPBITS=(serial.STOPBITS_ONE,serial.STOPBITS_ONE_POINT_FIVE,serial.STOPBITS_TWO)
	try:
		print("Available number of stop bits: "+str(STOPBITS)+".")
		stopbits=int(input("What number of stop bits to use (default: "+str(serial.STOPBITS_ONE)+")? "))
		if stopbits in STOPBITS:
			return stopbits
	except:
		pass
	print("WARNING: No or invalid stopbits specified: the default will be used!")
	return serial.STOPBITS_ONE
def getTimeout():
	try:
		timeout=float(input("What timeout (in seconds) to use (default: none)? "))
		if timeout>0:
			return timeout
	except:
		pass
	print("WARNING: No or an invalid timeout specified: no timeout will be used.")
	return None
def getXonxoff():
	return input("Use xon - xoff (default: False)? ") in ('Y','y')
def getRtscts():
	return input("Use rts - cts (default: False)? ") in ('Y','y')
def getWrite_timeout():
	try:
		write_timeout=float(input("What write timeout (in seconds) to use (default: none)? "))
		if write_timeout>0:
			return write_timeout
	except:
		pass
	print("WARNING: No or an invalid write timeout specified: no write timeout will be used.")
	return None
def getDsrdtr():
	return input("Use dsr - dtr (default: False)? ") in ('Y','y')
def getInter_byte_timeout():
	try:
		inter_byte_timeout=float(input("What inter-character timeout (in seconds) to use (default: none)? "))
		if inter_byte_timeout>0:
			return inter_byte_timeout
	except:
		pass
	print("WARNING: No or an invalid inter-character timeout specified: no inter-character timeout will be used.")
	return None
def getExclusive():
	return input("Use exclusive access mode (POSIX only) (default: False)? ") in ('Y','y')
	
def getSerialDataReader(inputDeviceName=None,report=True):
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
		print("No serial input device specified.")
		return None
	global serialCommunicators
	if not inputDeviceName in serialDataReaders or not serialDataReaders[inputDeviceName].isRunning():
		try:
			serialDataReaders[inputDeviceName]=SerialDataReader(serial.Serial(port=inputDeviceName,baudrate=getBaudrate(),bytesize=getBytesize(),parity=getParity(),stopbits=getStopbits(),timeout=getTimeout(),xonxoff=getXonxoff(),rtscts=getRtscts(),write_timeout=getWrite_timeout(),dsrdtr=getDsrdtr(),inter_byte_timeout=getInter_byte_timeout(),exclusive=getExclusive()),report)
		except Exception as ex:
			print("ERROR: '"+str(ex)+"' instantiating the reader to read serial data from port '"+inputDeviceName+"'.")
	return serialDataReaders[inputDeviceName]

def new():
	print("\nNew serial data reader creation")
	report=input("Do you want to store all reports (use the serial data reader method printReported() to print them)? ") in ['Y','y']
	return getSerialDataReader(None,report)
	
if __name__=="__main__":
	# try to get a communicator that starts immediately
	serialDataReader=new()
	if serialDataReader is not None:
		if serialDataReader.addByteRetriever(ByteRetriever()):
			serialDataReader.start()
		else:
			print("ERROR: Failed to add a basic serial data byte retriever.")
	else:
		print("ERROR: Failed to create a serial data reader created. Exiting now.")
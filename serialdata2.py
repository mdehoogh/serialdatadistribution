"""
MDH@02APR2019:
- SerialByteDispatcher reads the serial data from an associated serial port
  and informs ByteReaders about it

 """

# wrapping reading serial data in a class descending from a Thread
# so we can keep interfacing with this program while serial data is read and relayed
import _thread
import threading
import serial
import collections
import queue
import sys
import time
import datetime
import socket

__DEBUG__=False

# a ByteSource wraps bytes in BytesRead which remembers when it was created (in self.time)
class BytesRead(bytearray):
	# if we override super's append I cannot call append directly...
	def appendBytes(self,bytes_):
		l=len(self)
		try:
			for byte in bytes_:
				self.append(byte)
		except:
			pass
		# return the amount appended...
		return len(self)-l
	def __init__(self,bytes_=None,time_=None):
		if not isinstance(time_,float):
			self.__time=time.time()
		else:
			self.__time=time_
		if isinstance(bytes_,bytes):
			super().__init__(bytes_)
		else:
			super().__init__()
	def getTime(self):
		return self.__time
	def getBytes(self):
		return bytes(self) # return immutable version of my contents!!
	def __str__(self):
		return str(datetime.datetime.fromtimestamp(self.__time))+"\t"+str(self.getBytes())
	def __repr__(self):
		return self.__str__()

class Reporter:
	def __init__(self,echo=False):
		self.__echo=echo
		self.__reportIndex=0
		self.__reportQueue=queue.Queue()
	def _reporting(self,report):
		if report is not None:
			self.__reportIndex+=1
			self.__reportQueue.put_nowait(str(datetime.datetime.fromtimestamp(time.time()))+"\t"+str(self.__reportIndex)+"\t"+str(report))
			if self.__echo:
				print(str(report))
	def report(self,reportcountflag=False):
		reportCount=0
		try:
			# will wear itself out eventually
			while True:
				print(self.__reportQueue.get_nowait())
				reportCount+=1
		except:
			pass
		if reportcountflag:
			if reportCount:
				print(str(reportCount)+" reported messages printed!")
			else:
				print("No messages to report!")
	def toreport(self):
		return self.__reportQueue.qsize()
	def reported(self):
		return self.__reportIndex
	def __repr__(self):
		return "Reported: "+str(self.reported())+" - reportable: "+str(self.toreport());

# a ByteConsumer implements consumed() to process a BytesRead instance, passed to it by a ByteProducer
class ByteConsumer(Reporter):
	def __init__(self,echo=False):
		super().__init__(echo)
		# as a service keep track of how many BytesRead were consumed and the last BytesRead consumed..
		self.__consumedIndex=0
		self.__consumed=None
	def consumed(self,bytesRead):
		if isinstance(bytesRead,BytesRead):
			try:
				self.__consumed=bytesRead
				self.__consumedIndex+=1
				return True
			except:
				super()._reporting("ERROR: '"+str(ex)+"' consuming '"+str(bytesRead)+"'.")
		return False
	def __repr__(self):
		result=super().__repr__()
		if self.__consumed:
			result+=" - #"+str(self.__consumedIndex)+": '"+str(self.__consumed)
		return result

class UDPByteConsumer(ByteConsumer):
	def __init__(self,destinationPort,destinationIPAddress='127.0.0.1'):
		super().__init__(__DEBUG__) # let's echo when debugging
		self.__destination=(destinationIPAddress,destinationPort)
		self.__udpSocket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM) # UDP socket
	def consumed(self,bytesRead):
		if super().consumed(bytesRead):
			try:
				bytesReadText=str(bytesRead)
				# we're NOT sending the timestamp along!!!!
				bytesReadbytes=bytesRead.getBytes()
				"""
				bytesReadbytes=bytes(bytesReadText,'ascii') # convert to a bytes object to send along...
				"""
				bytesSent=self.__udpSocket.sendto(bytesReadbytes,self.__destination)
				if bytesSent==len(bytesReadbytes): # all bytes sent
					return True
				super()._reporting("ERROR: Only "+str(bytesSent)+" out of "+str(len(bytesReadbytes))+" bytes sent to "+str(self.__destination)+".")
			except Exception as ex:
				super()._reporting("ERROR: '"+str(ex)+"' in sending '"+bytesReadText+"'' to "+str(self.__destination)+".")
		else:
			super()._reporting("ERROR: No or invalid BytesRead to consume!")
		#####print("ERROR: Consuming '"+str(bytesRead)+"' failed.")
		return False

# a ByteProducer knows it byte consumer to push along what it receives
# LineByteConsumer cuts out the line ends but does not send what it receives along
class LineByteConsumer(ByteConsumer):

	def __init__(self,sepbytes=b'\r\n',maxsepcount=2):
		super().__init__()
		if not isinstance(sepbytes,bytes) or len(sepbytes)==0:
			raise Exception("Invalid line separators.")
		self.__sepbytes=sepbytes
		self.__maxsepcount=maxsepcount
		self.__line=None
		self.__linesep=None

	# _pushed() is actually a ByteProducer method
	def _pushed(self,bytesRead):
		# I suppose without a next byte processor we can simply print it, or even better report it
		self._reporting("Line '"+str(bytesRead)+"'.");
		return True	# my implementation of _processed calls _passedAlong for any line

	def __pushLine(self):
		if self.__line: # something to push along
			if not self._pushed(self.__line): # failed to push along what we have to push along
				self.__line.appendBytes(self.__linesep)
				self.__linesep=bytearray()
			else:
				self.__line=None

	def __newline(self,time):
		self.__line=BytesRead(time_=time) # using the time passed in to initialize the BytesRead with
		self.__linesep=bytearray() # keep track of the current separator

	def _processed(self,bytesRead):
		#####print("Processing '"+str(bytesRead)+"'...")
		result=False
		try:
			# if we do not have a line yet, get one with the timestamp of what we are to process!!!
			if not self.__line:
				self.__newline(bytesRead.getTime())
			for byteRead in bytesRead:
				if byteRead in self.__sepbytes: # a line separator byte
					self.__linesep.append(byteRead)
					if self.__maxsepcount>0 and len(self.__linesep)>=self.__maxsepcount: # end of line
						self.__pushLine()
				else: # not a line separator byte
					if len(self.__linesep): # we're in a line separator, the received byte starts a new line
						self.__pushLine()
					# we need a BytesRead instance in self.__line to append our byte to
					if not self.__line:
						self.__newline(bytesRead.getTime())
					self.__line.append(byteRead)
			result=True
		except Exception as ex:
			self._reporting("ERROR: '"+str(ex)+"' extracting lines from "+str(bytesRead)+".")
		return result

	def consumed(self,producedBytesRead):
		return super().consumed(producedBytesRead)and self._processed(producedBytesRead)

class ByteProducer(Reporter):
	def setByteConsumer(self,byteConsumer):
		if __DEBUG__:
			if byteConsumer:
				print("Setting the byte consumer to '"+str(byteConsumer)+"!")
			else:
				print("No byte consumer to set!")
		self._byteConsumer=(None,byteConsumer)[isinstance(byteConsumer,ByteConsumer)]
		if __DEBUG__:
			if self._byteConsumer:
				print("Byte consumer set to '"+str(self._byteConsumer)+"!")
			else:
				print("No byte consumer set!")
		return self
	def __init__(self,byteConsumer=None):
		super().__init__()
		self.setByteConsumer(byteConsumer)
	def getByteConsumer(self):
		return self._byteConsumer
	# call _pushed() to push along what was produced
	def _pushed(self,producedBytesRead):
		return self._byteConsumer is None or self._byteConsumer.consumed(producedBytesRead)

# a ByteProcessor is both a ByteProducer and a ByteConsumer
class ByteProcessor(ByteProducer,ByteConsumer):
	def __init__(self,nextByteConsumer):
		ByteProducer.__init__(self,nextByteConsumer)
		ByteConsumer.__init__(self)
		self._processedBytesRead=None # holds on to the processed bytes read until they are consumed
	def _processed(self,bytesRead):
		if self._byteConsumer:
			if self._processedBytesRead:
				self._processedBytesRead.appendBytes(bytesRead.getBytes())
			else: # make a copy
				self._processedBytesRead=bytesRead.copy()
			if self._pushed(self._processedBytesRead):
				self._processedBytesRead=None
		# assume to be successful if self._processedBytesRead is now None!!
		return self._processedBytesRead is None
	# consumed() is overridden to send along what was received
	def consumed(self,bytesRead):
		result=False
		if super().consumed(bytesRead): # valid (and registered) input
			try:
				if self._processed(bytesRead):
					result=True
			except Exception as ex:
				super()._reporting("ERROR: '"+str(ex)+"' in processing '"+str(bytesRead)+"'.")
		return result

class LineByteProcessor(LineByteConsumer,ByteProducer):
	def __init__(self,nextByteProcessor=None,sepbytes=b'\r\n',maxsepcount=2):
		LineByteConsumer.__init__(self,sepbytes,maxsepcount)
		ByteProducer.__init__(self,nextByteProcessor)
	
	def _pushed(self,bytesRead):
		if self._byteConsumer:
			return self._byteConsumer.consumed(bytesRead)
		print("No byte consumer to push to!")
		return super()._pushed(bytesRead)

# ByteSource receives the raw bytes in its _register method and is the first element in the chain of byte processors, so immediately pushes it along to the associated byte processor
class ByteSource(ByteProducer):
	def __init__(self,byteConsumer):
		super().__init__(byteConsumer)
		self.__bytesRead=None
	def _registered(self,bytes):
		# the issue here is that we do not want to loose any bytes received...
		result=False
		try:
			if self.__bytesRead is None:
				self.__bytesRead=BytesRead(bytes)
			else:
				self.__bytesRead.appendBytes(bytes)
			# if we manage to push the constructed __bytesRead along, we can get rid of self.__bytesRead
			if self._pushed(self.__bytesRead):
				self.__bytesRead=None
		except Exception as ex:
			self._reporting("ERROR: '"+str(ex)+"' in registering '"+str(bytes)+"' by byte source '"+str(self)+"'.")
		return self.__bytesRead is None

# ByteSink is what a ByteDispatcher dispatches to which has a relationship with 
class ByteSink(ByteProcessor):
	
	def __init__(self,name,_nextByteProcessor):
		super().__init__(_nextByteProcessor)
		self.__name=name # remember the name
		self._bytesReadCount=0
	
	def update(self):
		if self.__byteDispatcher:
			self._bytesReadAvailable=self.__byteDispatcher.getBytesReadCount()
			# push all we can immediately
			while self._bytesReadCount<self._bytesReadAvailable:
				if not self.processed(self.__byteDispatcher.getBytesRead(self._bytesReadCount)):
					break
				self.bytesReadCount+=1 # one less to retrieve

	def setByteDispatcher(self,byteDispatcher):
		self.__byteDispatcher=byteDispatcher
		if self.__byteDispatcher:
			self._bytesReadCount=self.__byteDispatcher.getNumberOfDisposedBytesRead() # can't (and won't) read what isn't there anymore...
			self.update() # force an update to get up to speed!!!

	def getBytesReadCount(self): # should be available to the dispatcher at all times...
		return self._bytesReadCount
	
	def __str__(self):
		return self.__name
	
	def __repr__(self):
		return self.__name+" ("+str(self._bytesReadCount)+" of "+str(self._bytesReadAvailable)+" read)"

#ByteDispatcher is a special type of ByteProcessor that collects the BytesRead instances it receives, only informing its ByteSinks
# so as opposed to ByteProcessor it has to keep its received BytesRead packets until they are requested
class ByteDispatcher(ByteSink):

	def __init__(self,_name,_nextByteProcessor=None): # typically won't have a next byte processor just ByteSinks
		super().__init__(_name,_nextByteProcessor) # can have a next but unlikely
		self.__byteSinks={} # keep a dictionary of byte sinks (by name)
		self.__bytesReadList=collections.deque() # a thread-safe list i.e. supporting atomic actions

	def getNumberOfDisposedBytesRead(self):
		return self._bytesReadCount-len(self.__bytesReadList)

	def _cleanup(self):
		# cleans up the list of BytesRead instances
		minSinkBytesReadCount=len(self.__bytesReadList) # the maximum number of disposable BytesRead instances
		if minSinkBytesReadCount: # something in the BytesRead list right now
			if len(self.__byteSinks): # we have byte sinks not up to date
				bytesReadDisposed=self.getNumberOfDisposedBytesRead() # the number of BytesRead instances disposed
				for byteSink in self.__byteSinks.values():
					sinkBytesReadCount=byteSink.getBytesReadCount()-bytesReadDisposed # what was read since the last disposal (MUST be zero or positive!!)
					if sinkBytesReadCount<minSinkBytesReadCount:
						minSinkBytesReadCount=sinkBytesReadCount
				if minSinkBytesReadCount>0:
					self._reporting("Will remove "+str(minSinkBytesReadCount)+" BytesRead instances.")
					while minSinkBytesReadCount>0:
						minSinkBytesReadCount-=1
						self.__bytesReadList.popleft()
				else:
					self._reporting("No BytesRead to remove.")
			else: # I guess we can get rid of the entire contents...
				self.__bytesReadList.clear()
	def getBytesRead(self,index):
		# NOTE index is an absolute index unless it's negative
		try:
			if index>=0:
				index-=self.getNumberOfDisposedBytesRead()
			return self.__bytesReadList[index]
		except:
			self._reporting("ERROR: '"+str(ex)+"' returning bytes read #"+str(index)+" by dispatcher "+self.name+".")
		return None

	def processed(self,bytesRead):
		result=False
		if isinstance(bytesRead,BytesRead):
			try:
				self.__bytesReadList.append(bytesRead)
				self._bytesReadCount+=1 # another one available...
				# tell all byte sinks to update themselves
				for byteSink in self.__byteSinks.values():
					try:
						byteSink.update()
					except:
						pass

				result=super().processed(_bytesReadList[-1]) # push along the last element in the list
			except Exception as ex:
				self._reporting("ERROR: '"+str(ex)+"' processing '"+str(bytesRead)+".")
		self._cleanup() # TODO under what condition should we cleanup????
		return result

	# ByteSinks support
	def removeByteSinkWithName(self,byteSinkName):
		if not isinstance(byteSinkName,str):
			raise Exception("Undefined or invalid byte sink name!")
		if byteSinkName in self.__byteSinks:
			try:
				self.__byteSinks[byteSinkName].setByteDispatcher(None)
				del self.__byteSinks[byteSinkName] # might fail if it wasn't present to start with
				self._reporting("Byte sink with name '"+byteSinkName+"' removed!")
			except:
				self._reporting("ERROR: Failed to remove byte sink '"+byteSinkName+"' from the list of byte sinks of dispatcher '"+self.name+"'.")
		return not byteSinkName in self.__byteSinks # if not present (anymore), remove its reference to me
	def removeByteSink(self,byteSink):
		for byteSinkName in self.__byteSinks.keys():
			if byteSink==self.__byteSinks[byteSinkName]:
				return self.removeByteSinkWithName(byteSinkName)
		return False
	def addByteSink(self,byteSink,byteSinkName=''):
		if not isinstance(byteSinkName,str) or not isinstance(byteSink,ByteSink):
			raise Exception("Undefined/invalid byte sink or byte sink name!")
		# needs to be a ByteReader to start with
		result=False
		if not byteSinkName in self.__byteSinks: # not currently registered (under that name)
			try:
				self.__byteSinks[byteSinkName]=byteSink
				byteSink.setByteDispatcher(self) # won't raise an exception because the input is not invalid
				result=True
			except Exception as ex:
				self._reporting("ERROR: '"+str(ex)+"' in adding byte sink '"+byteSinkName+"' to the list of byte sinks of dispatcher '"+self.name+"'.")
		elif self.__byteSinks[_byteSinkName]==_byteSink: # already have it!!!
			result=True
		else:
			self._reporting("ERROR: Another byte sink called '"+byteSinkName+"' already registered with dispatcher '"+self.name+"'.")
		return (None,_byteSink)[result]

	def getByteSink(self,byteSinkName=''):
		if isinstance(byteSinkName,str):
			# add the anonymous byte reader (with empty name) JIT 
			if len(byteSinkName)==0 and not '' in self.__byteSinks:
				if self.addByteSink(ByteSink()) is None:
					self._reporting("ERROR: Failed to add the default byte sink!")
			if byteSinkName in self.__byteSinks:
				return self.__byteSinks[byteSinkName]
		return None
	def getByteSinkNames(self):
		return self.__byteSinks.keys()		

# culmunating in SerialByteSource which acts as a ByteSource to a serial input device (of type Serial.serial)
class SerialByteSource(ByteSource):

	def __init__(self,serialInputDevice):
		super().__init__(None)
		if not isinstance(serialInputDevice,serial.Serial):
			raise Exception("No (proper) serial input device specified.")
		self.__serialInputDevice=serialInputDevice
		self.__name=serialInputDevice.name # even if we kill the reference
		self.__thread=None
		self.__paused=False
		self.__running=False
		self.__numberOfBytesRead=0 # count the number of bytes read...

	def __del__(self):
		if self.__thread:
			self.__thread=None # this will force disposing of the serial input device for good...
			# ascertain to be closed!!
			self.stop()
	
	def __run(self,_sleep):
		if self.__serialInputDevice is not None:
			# let's get a reference to the running thread, if we remove it on destroying, gets rid of the serialInputDevice!!
			self.__thread=threading.current_thread()
			self._reporting("'"+self.__name+"' will start running...")
			self.__paused=False
			self.__running=True
			# keep reading as long as the serial input device is (still) open
			while self.__running:
				if self.__serialInputDevice.isOpen:
					if self.__serialInputDevice.out_waiting:
						self.__serialInputDevice.flush() # write everything that can be written
					# when paused, assume nothing to read...
					numberOfBytesToRead=(self.__serialInputDevice.in_waiting,0)[self.__paused]
					if numberOfBytesToRead:
						if self._registered(self.__serialInputDevice.read(size=numberOfBytesToRead)):
							self.__numberOfBytesRead+=numberOfBytesToRead
						else:
							self._reporting("ERROR: Failed to register "+str(numberOfBytesToRead)+" serial bytes read.")
					if _sleep>0:
						time.sleep(_sleep)
				else:
					self._reporting("Serial input device (still) not open!")
					time.sleep(1)
			self._reporting("'"+self.__name+"' finished running...")
			self.__close() # as soon as the loop ends close the serial port connection as well...
		else:
			self._reporting("Can't start '"+self.__name+"': no associated serial input device (anymore).")

	def __close(self):
		# deciding NOT to dispose of self.serialInputDevice unless self.__thread is no longer defined!!!
		if self.__serialInputDevice:
			try:
				if self.__serialInputDevice.isOpen:
					self.__serialInputDevice.flushInput() # TODO should we do this?????
					self.__serialInputDevice.flushOutput() # TODO should we do this?????
					self.__serialInputDevice.close()
					self._reporting("Connection to '"+self.name+"' closed.")
			except Exception as ex:
				self._reporting("ERROR: '"+str(ex)+"' closing the connection to '"+self.__name+"'.")
			finally: # ascertain to remove the reference
				if not self.__thread: # no thread registered anymore...
					self.__serialInputDevice=None
		
	def __str__(self):
		# when working let's also show the first and last index we have in store
		return self.__name+' '+(('DONE','IDLE')[self.isRunnable()],('READING','PAUSING')[self.__paused]+' [read: '+str(self.__numberOfBytesRead)+"]")[self.isRunning()] # appending - (done), + (runnable), * (running)
	
	def __repr__(self):
		return self.__str__()
		
	def isRunning(self):
		return self.__running

	def isRunnable(self):
		# considered runnable if it is not currently running and can be run...
		return not self.__running and self.__serialInputDevice is not None

	def isPaused(self):
		return self.__running and self.__paused

	def write(self,_bytes):
		if isinstance(_bytes,bytes):
			if self.__serialInputDevice is not None and self.__serialInputDevice.isOpen:
				return self.__serialInputDevice.write(_bytes)
		return 0
		
	# start() and stop()
	def start(self,_sleep=0.0):
		if not isinstance(_sleep,(int,float)) or _sleep<0:
			self._reporting("Sleep time invalid.")
			return None
		# can't run twice!!!
		if self.__serialInputDevice is None:
			self._reporting("Can't start '"+self.__name+"' again.")
			return None
		if self.__running:
			self._reporting("Can't start '"+self.__name+"': it has already started.")
		else: # start a new thread that executes __run
			# open the device (again) if not currently open!!!
			if not self.__serialInputDevice.isOpen:
				self._reporting("Opening the serial input device '"+self.__name+"'...")
				self.__serialInputDevice.open()
			_thread.start_new_thread(self.__run,(_sleep,))
		return self

	def stop(self):
		if self.__serialInputDevice is None:
			self._reporting("Can't stop '"+self.__name+"' again.")
			return False
		if not self.__running:
			# force a close if the serial input device is still open (as it would be if we didn't start at all!!)
			if self.__serialInputDevice.isOpen:
				self.__close()
			self._reporting("Can't stop '"+self.__name+"' it has already stopped.")
		else:
			self.__running=False
		return not self.__running

	def pause(self):
		if self.__running:
			self.__paused=True
		else:
			self._reporting("Can't pause '"+self.__name+"': not currently running!")
		return self.__paused
	def resume(self):
		if self.__running:
			self.__paused=False
		else:
			self._reporting("Can't resume '"+self.__name+"': not currently running!")
		return not self.__paused

# keep a dictionary of serial data dispatchers (by serial port name)
serialByteSources={}

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
	
def addSerial(_serial):
	if not isinstance(_serial,serial.Serial):
		raise Exception("No serial input device specified.")
	global serialByteSources
	if not _serial.port in serialByteSources or not serialByteSources[_serial.port].isRunning():
		try:
			serialByteSources[_serial.port]=SerialByteSource(_serial)
		except Exception as ex:
			print("ERROR: '"+str(ex)+"' instantiating the serial byte source to read serial bytes from port '"+_serial.port+"'.")
	if _serial.port in serialByteSources:
		return serialByteSources[_serial.port]
	return None

def getSerialByteSource(inputDeviceName=None):
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
	return addSerial(serial.Serial(port=inputDeviceName,baudrate=getBaudrate(),bytesize=getBytesize(),parity=getParity(),stopbits=getStopbits(),timeout=getTimeout(),xonxoff=getXonxoff(),rtscts=getRtscts(),write_timeout=getWrite_timeout(),dsrdtr=getDsrdtr(),inter_byte_timeout=getInter_byte_timeout(),exclusive=getExclusive()))

def new():
	return getSerialByteSource(None)

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
			serialByteSource=addSerial(serial.Serial(port=inputDeviceName,baudrate=getBaudrate(map['baudrate']),bytesize=getBytesize(map['bytesize']),parity=getParity(map['parity']),stopbits=getStopbits(map['stopbits']),timeout=getTimeout(map['timeout']),xonxoff=getXonxoff(map['xonxoff']),rtscts=getRtscts(map['rtscts']),write_timeout=getWrite_timeout(map['write_timeout']),dsrdtr=getDsrdtr(map['dsrdtr']),inter_byte_timeout=getInter_byte_timeout(map['inter_byte_timeout']),exclusive=getExclusive(map['exclusive'])))
			if serialByteSource is not None:
				if serialByteSource.start():
					while True:
						bytesRead=serialByteSource.read()
						if bytesRead is None: # something the matter????
							serialByteSource.printReported()
						else:
							print("Read: '"+str(bytesRead)+"'.")
						time.sleep(0.1) # sleep a little while
					print("Serial byte source not running anymore!")
				else:
					print("ERROR: Failed to start the serial byte source.")
			else:
				print("ERROR: Failed to create a serial byte source.")
		else:
			print("No serial input device specified.")
	else:
		print("Need at least the name of the serial input device! Any parameters should be presented on the command-line in the format <name>=<value> e.g. baudrate=9600!")		

def test():
	# try to get a dispatcher that starts immediately
	serialByteSource=getSerialByteSource(None)
	if serialByteSource is not None:
		serialByteSource.start()
		serialByteSource.printReported()
		if serialByteSource.isRunning():
			print("Serial byte source to serial port '"+serialByteSource.serialInputDevice.name+"' up and running...")
		else:
			print("WARNING: Serial byte source to serial port '"+serialByteSource.serialInputDevice.name+"'  NOT  up and running...")
	else:
		print("ERROR: Failed to create a serial byte source.")

if __name__=='__main__':
	main(sys.argv[1:])
else:
	print("Call serialdata2.new() to obtain a serial byte source.")
	print("Predefined byte processor classes: ByteProcessor and LineByteProcessor.")

	
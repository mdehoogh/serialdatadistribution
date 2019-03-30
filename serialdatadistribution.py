"""
MDH@29MAR2019:
- Python program to receive data on a serial port and pass it along to a number of 'line readers'
- getDistributor() arguments:
  1. name of serial input device
  2. report flag (default True): if True, creates a default Reporter that will write to the console, use setReporter() otherwise
  3. start flag (default: False): if True, starts immediately (otherwise start() is to be called)
MDH@30MAR2019:
- keeping a list of received lines inside SerialDataDistributor for polling purposes
- newDistributor() will ask whether to use a default reporter and whether or not to start immediately
"""

# wrapping reading serial data in a class descending from a Thread
# so we can keep interfacing with this program while serial data is read and relayed
import threading
import serial
import time
import queue

"""
OUTPUT: TCP SERVER AND ITS CLIENTS
Clients should tells us who they are and what data they are interested in
So in response to telling us who they are we return a list of active distributors to choose from
"""

"""
END OF OUTPUT
"""
 
"""
INPUT: SERIAL DATA DISTRIBUTOR
"""
class Reporter:
	def report(self,_report):
		print(_report)

class LineReader(list):
	def __init__(self):
		list.__init__(self)
	def read(self,_read):
		self.append(_read)
		print("Line #"+str(len(self))+": '"+_read+"'.")
		
class SerialDataDistributor(threading.Thread):
	def __report(self,toreport):
		if self.reporter is not None:
			self.reporter.report(toreport)
	def isRunnable(self):
		# considered runnable if it is not currently running and can be run...
		return not self.running and self.serialInputDevice is not None
	def __init__(self,_serialInputDevice,_report=True,_start=False):
		threading.Thread.__init__(self) # can parent class constructor
		if not isinstance(_serialInputDevice,serial.Serial):
			raise Exception("No (proper) serial input device specified.")
		if not _serialInputDevice.isOpen:
			raise Exception("Serial input device '"+_serialInputDevice.name+"' is not open.")
		self.running=False
		self.lines=queue.Queue() # the list of received lines
		self.lastChar='\0'
		self.line="" # the line composed so far
		self.lineReaders=[] # no line reader(s) so far
		self.lineReaderCount=0
		if _report:
			self.reporter=Reporter() # by default write to console
		else:
			self.reporter=None
		self.serialInputDevice=_serialInputDevice
		self.name=self.serialInputDevice.name # even if we kill the reference
		# start reading from the serial input device
		if _start:
			self.start()
	def __del__(self):
		# ascertain to be closed!!
		self.close()
	
	# how many lines are there still?
	def getLinesAvailable(self):
		if self.lines.empty():
			return 0
		return self.lines.qsize()
		
	def getLine(self):
		if not self.lines.empty():
			try:
				# return if a line is immediately available (i.e. don't block)
				return self.lines.get_nowait()
			except:
				pass
		return None
		
	def __process_line(self,_line):
		try:
			self.lines.put_nowait(_line) # store the line received
		except Queue.Full:
			self.__report("ERROR: Lines queue is full!")
		if self.lineReaderCount:
			for lineReader in self.lineReaders:
				try:
					lineReader.read(_line)
				except:
					pass
		elif self.reporter:
			self.reporter.report("Read: '"+_line+"'.")
	
	def __process_bytes(self,_bytes):
		try:
			for _byte in _bytes:
				_char=chr(_byte)
				self.line+=_char
				if _char=='\n' and self.lastChar=='\r':
					try:
						self.__process_line(self.line[:-2])
					finally:
						self.line=""
				# remember the last byte received...
				self.lastChar=_char
		except Exception as ex:
			self.__report("ERROR: '"+str(ex)+"' processing "+str(len(_bytes))+" bytes received from '"+self.name+"'.")
	def isRunning(self):
		return self.running
	def run(self):
		self.running=True
		# keep reading as long as the serial input device is (still) open
		while self.serialInputDevice:
			if self.serialInputDevice.out_waiting:
				self.serialInputDevice.flush() # write everything that can be written
			numberOfBytesToRead=self.serialInputDevice.in_waiting
			if numberOfBytesToRead:
				self.__process_bytes(self.serialInputDevice.read(size=numberOfBytesToRead))
			"""
				self.__report("Reading "+str(numberOfBytesToRead)+" bytes from '"+self.name+"'...")
			else:
				self.__report("Nothing to read from '"+self.name+"'...")
			"""
			time.sleep(1)
		self.running=False
		self.__report("'"+self.name+"' stopped running...")
	def __str__(self):
		return self.name+((' FINISHED',' IDLE')[self.isRunnable()],' WORKING')[self.isRunning()] # appending - (done), + (runnable), * (running)
	def __repr__(self):
		return self.__str__()
		
	def write(self,_bytes):
		if isinstance(_bytes,bytes):
			if self.serialInputDevice.isOpen:
				return self.serialInputDevice.write(_bytes)
		return 0
		
	def close(self):
		# ascertain to close only once
		if self.serialInputDevice:
			try:
				self.serialInputDevice.flushOutput() # TODO should we do this?????
				self.serialInputDevice.close()
				self.__report("Connection to '"+self.name+"' closed.")
			except Exception as ex:
				self.__report("ERROR: '"+str(ex)+"' closing the connection to '"+self.name+"'.")
			finally: # ascertain to remove the reference
				self.serialInputDevice=None
		return self
		
	# makes more sense to have a stop() instead of a close()
	def stop(self):
		return self.close()
		
	def setReporter(self,_reporter):
		if _reporter is not None:
			if not hasattr(_reporter,'report') or type(_reporter.report)!="<class 'method'>":
				raise Exception("Reporter does not have a report() method.")
		self.reporter=_reporter
		return self
		
	def deleteLineReaderWithIndex(self,_lineReaderIndex):
		# can't actually remove
		try:
			if self.lineReaders[_lineReaderIndex-1] is not None:
				self.lineReaders[_lineReaderIndex-1]=None
				self.lineReaderCount-=1 # one registered line reader left...
				self.__report("Number of line readers associated with '"+self.name+"': "+str(self.lineReaderCount)+".")
		except:
			pass
	def addLineReader(self,_lineReader):
		if _lineReader is None or not hasattr(_lineReader,'read') or type(_lineReader.read)!="<class 'method'>":
			raise Exception("Undefined line reader or line reader that does not have a read() method.")
		self.lineReaders.append(_lineReader)
		self.lineReaderCount+=1 # another line reader...
		self.__report("Number of line readers associated with '"+self.name+"': "+str(self.lineReaderCount)+".")
		return len(self.lineReaders)
			
# keep a dictionary of serial data distributors (by name)
serialDataDistributors={}

# function for getting serial device parameter values
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
	
def getDistributor(inputDeviceName=None,report=True,start=False):
	# is there a default device?
	if not isinstance(inputDeviceName,str):
		inputDeviceName=None
		# show a list of serial input devices to choose from (in groups of 9)
		import serial.tools.list_ports
		serialPortInfos=serial.tools.list_ports.comports()
		if serialPortInfos is not None and len(serialPortInfos)>0:
			# show serial ports in groups of at most 9 options
			serialPortInfoIndex=0
			while serialPortInfoIndex<len(serialPortInfos):
				for optionIndex in range(1,10):
					if serialPortInfoIndex+optionIndex>len(serialPortInfos):
						break
					serialPortInfo=serialPortInfos[serialPortInfoIndex+optionIndex-1]
					print(str(optionIndex)+"."+str(serialPortInfo.device))
				while 1:
					selectedOption=input("What is the number of the serial port to use? ")
					# if no option was selected go and show the next one
					if len(selectedOption)==0:
						break
					try:
						selectedOptionIndex=int(selectedOption)
						if selectedOptionIndex>0 and selectedOptionIndex+serialPortInfoIndex<=len(serialPortInfos):
							inputDeviceName=serialPortInfos[selectedOptionIndex+serialPortInfoIndex-1].device
							break
					except Exception as ex:
						print("ERROR: '"+str(ex)+"' processing selected option '"+selectedOption+"'.")
				if inputDeviceName is not None:
					break
				serialPortInfoIndex+=9
		else:
			print("No serial devices available.")
	if inputDeviceName is None:
		print("No serial input device specified.")
		return None
	global serialDataDistributors
	if not inputDeviceName in serialDataDistributors or not serialDataDistributors[inputDeviceName].isRunning():
		try:
			serialDataDistributors[inputDeviceName]=SerialDataDistributor(serial.Serial(port=inputDeviceName,baudrate=getBaudrate(),bytesize=getBytesize(),parity=getParity(),stopbits=getStopbits(),timeout=getTimeout(),xonxoff=getXonxoff(),rtscts=getRtscts(),write_timeout=getWrite_timeout(),dsrdtr=getDsrdtr(),inter_byte_timeout=getInter_byte_timeout(),exclusive=getExclusive()),report,start)
		except Exception as ex:
			print("ERROR: '"+str(ex)+"' instantiating the serial device called '"+inputDeviceName+"'.")
	return serialDataDistributors[inputDeviceName]

def newDistributor():
	report=input("Do you want to use a default reporter? ") in ['Y','y']
	start=input("Do you want the distributor to start immediately? ") in ['Y','y']
	return getDistributor(None,report,start)
	
if __name__=="main":
	# try to get a distributor
	distributor=getDistributor()
	if distributor is not None:
		pass # TODO what should we do here????
	else:
		print("No distributor created. Exiting now.")
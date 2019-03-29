"""
MDH@29MAR2019:
- Python program to receive data on a serial port and pass it along to a number of registered 'apps'

"""

# wrapping reading serial data in a class descending from a Thread
# so we can keep interfacing with this program while serial data is read and relayed
import threading
import serial
import time

class Reporter:
	def report(self,toreport):
		print(toreport)

class LineReader(list):
	def __init__(self):
		list.__init__(self)
	def read(self,_read):
		self.append(_read)
		print("Line #"+str(len(self))+": '"+_read+"'.")
		
class SerialDataDistributor(threading.Thread):
	def report(self,toreport):
		if self.reporter is not None:
			self.reporter.report(toreport)
	def isActive(self):
		return self.serialInputDevice is not None
	def __init__(self,_serialInputDevice,_start=False):
		threading.Thread.__init__(self) # can parent class constructor
		if not isinstance(_serialInputDevice,serial.Serial):
			raise Exception("No (proper) serial input device specified.")
		if not _serialInputDevice.isOpen:
			raise Exception("Serial input device '"+_serialInputDevice.name+"' is not open.")
		self.lastChar=0
		self.line="" # the line composed so far
		self.lineReader=None # no line reader so far
		self.reporter=Reporter() # by default write to console
		self.serialInputDevice=_serialInputDevice
		self.name=self.serialInputDevice.name # even if we kill the reference
		# start reading from the serial input device
		if _start:
			self.start()
	def __del__(self):
		# ascertain to be closed!!
		self.close()
	def process_bytes(self,_bytes):
		try:
			for _byte in _bytes:
				_char=chr(_byte)
				self.line+=chr(_byte)
				if chr(_byte)=='\n' and self.lastByte==ord('\r'):
					try:
						if self.lineReader:
							self.lineReader.read(self.line[:-2])
						elif self.reporter:
							self.reporter.report("Read: '"+self.line[:-2]+"'.")
					finally:
						self.line=""
				# remember the last byte received...
				self.lastByte=_byte
		except Exception as ex:
			self.report("ERROR: '"+str(ex)+"' processing "+str(len(_bytes))+" bytes received from '"+self.name+"'.")
	
	def run(self):
		# keep reading as long as the serial input device is (still) open
		while self.serialInputDevice:
			if self.serialInputDevice.out_waiting:
				self.serialInputDevice.flush() # write everything that can be written
			numberOfBytesToRead=self.serialInputDevice.in_waiting
			if numberOfBytesToRead:
				self.report("Reading "+str(numberOfBytesToRead)+" bytes from '"+self.name+"'...")
				self.process_bytes(self.serialInputDevice.read(size=numberOfBytesToRead))
			else:
				self.report("Nothing to read from '"+self.name+"'...")
			time.sleep(1)
		self.report("'"+self.name+"' stopped running...")
	def __str__(self):
		return self.name+['','*'](self.isActive()) # appending * if we're up and running!!!
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
				self.report("Connection to '"+self.name+"' closed.")
			except Exception as ex:
				self.report("ERROR: '"+str(ex)+"' closing the connection to '"+self.name+"'.")
			finally: # ascertain to remove the reference
				self.serialInputDevice=None
		return self
	def setReporter(self,_reporter):
		self.reporter=_reporter
		return self
	def setLineReader(self,_lineReader):
		self.lineReader=_lineReader
		return self
			
# keep a dictionary of serial data distributors (by name)
serialDataDistributors={}

def getDistributor(inputDeviceName=None):
	# is there a default device?
	if not isinstance(inputDeviceName,str):
		inputDeviceName=None
		# show a list of serial input devices to choose from (in groups of 9)
		import serial.tools.list_ports
		serialPortInfos=serial.tools.list_ports.comports()
		if serialPortInfos is not None or len(serialPortInfos)>0:
			# show serial ports in groups of at most 9 options
			serialPortInfoIndex=0
			while serialPortInfoIndex<len(serialPortInfos):
				for optionIndex in range(1,10):
					if serialPortInfoIndex+optionIndex>=len(serialPortInfos):
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
	if not inputDeviceName in serialDataDistributors or not serialDataDistributors[serialDataDistributor].isRunning():
		try:
			serialDataDistributors[inputDeviceName]=SerialDataDistributor(serial.Serial(port=inputDeviceName))
		except Exception as ex:
			print("ERROR: '"+str(ex)+"' instantiating the serial device called '"+inputDeviceName+"'.")
	return serialDataDistributors[inputDeviceName]
	
if __name__=="main":
	# try to get a distributor
	distributor=getDistributor()
	if distributor is not None:
		pass # TODO what should we do here????
	else:
		print("No distributor created. Exiting now.")
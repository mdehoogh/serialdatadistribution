MDH@08APR2019:

Example serialdata2 module usage:

import serialdata2

l=serialdata2.LineByteProcessor()

s=serialdata2.new().setByteProcessor(l).start()

# call l.report() repeatedly to view the extracted lines

# call s.stop() to stop the SerialByteSource, or s.pause() and s.resume() to pause/resume the SerialByteSource
s.stop()

General usage:
serialdata2.new() helps you create a SerialByteSource instance that descends from ByteSource.
ByteSource is a class that wraps the bytes received in a BytesRead instance (which is timestamped).
ByteSource and ByteProcessor instances allow setting a (next) ByteProcessor in the constructor.
ByteSource and ByteProcessor immediately push their received BytesRead instance to the next ByteProcessor by calling the processed() method of the next ByteProcessor.
ByteDispatcher descends ByteProcessor as well but keeps all the BytesRead instances it receives in a queue, that registered BytesSink instances can request (pull).
ByteSink descends ByteProcessor as well but have a getNumberOfBytesRead() method for ByteDispatcher() to call to determine how many BytesRead were processed so far.
ByteDispatchers removes all BytesRead instances no longer required by all its ByteSink instances.

MDH@05APR2019:

Example serialdata module usage (to be entered one line at a time in Python3 interactive mode):

import serialdata

# make a line byte reader
r=serialdata.new().addByteReader(serialdata.LineByteReader())

# keep popping
import time
for i in iter(r):
	if i is None:
		r.report()
	else:
		print(str(i))
	time.sleep(0.01) # hope to keep up

# abort using Ctrl-C
# stop the 'source'
r.getSource().stop()

# stop the reader
r.stop()

# done

MDH@29MAR2019:

Example serialdatadistribution usage:

import serialdatadistribution

# get a distributor optional passing in the name of the serial device (or None) and start flag (2nd argument) which defaults to False
d=serialdatadistribution.getDistributor()

# set reporter/line reader and start
# NOTE by default a serialdatadistribution.Reporter instance is used which will write the reported messages to the console
d.setReporter(None).setLineReader(serialdatadistribution.LineReader()).start()

# write something (to trigger responses?)
d.write(b'anything\r\n')

# bytes read is received as text either by the line reader (in chunks of lines without the CRLF) or reporter (if set).

# close the connection to the serial device
d.close()

# you can make as many distributors as you want to (well,for each of the serial ports available)

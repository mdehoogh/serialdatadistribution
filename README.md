MDH@29MAR2019: start

Use:


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

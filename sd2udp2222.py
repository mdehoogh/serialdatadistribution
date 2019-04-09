import serialdata2 as sd2

s=sd2.new().setByteConsumer(sd2.LineByteProcessor(sd2.UDPByteConsumer(2222))).start()

print("Run sd2udp2222server.py in another terminal window to receive the serial data.")

print("Call stop() to stop, pause() to pause, and resume() to resume.")

def stop():
	global s
	return s.stop()

def pause():
	global s
	return s.pause()

def resume():
	global s
	return s.resume()

def getByteConsumers():
	global s
	l=s.getByteConsumer()
	u=l.getByteConsumer()
	return (l,u)
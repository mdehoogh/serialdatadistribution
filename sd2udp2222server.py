# server-side part of example sd2udp2222

import socket
import sys

# Create a UDP socket
sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)

# Bind the socket to the port
sock.bind(('127.0.0.1', 2222))

print('\nReady to receive messages.')

while True:
    (data,address)=sock.recvfrom(1024)
    print("Received: '"+str(data)+"'.")
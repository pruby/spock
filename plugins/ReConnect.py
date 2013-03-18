from spock.mcp.mcpacket import Packet
from spock.net.cflags import cflags
from time import sleep

#Will relentlessly try to reconnect to a server
class ReConnectPlugin:
	def __init__(self, client):
		self.client = client
		client.register_handler(self.reconnect, 
			cflags['SOCKET_ERR'], cflags['SOCKET_HUP'], cflags['LOGIN_ERR'], cflags['AUTH_ERR'])
		self.delay = 1.17
		client.register_dispatch(self.reconnect, 0xFF)
		client.register_dispatch(self.grab_host, 0x02)
		client.register_dispatch(self.reset_reconnect_time, 0x03)

	def reconnect(self, *args):
		sleep(self.delay)
		if self.delay < 300:
			self.delay = self.delay * 2
		self.client.login(self.host, self.port)

	def reset_reconnect_time(self, *args):
		self.delay = 1.17

	#Grabs host and port on handshake
	def grab_host(self, packet):
		self.host = packet.data['host']
		self.port = packet.data['port']

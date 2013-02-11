#Constantly Changing, just a plugin I use to debug whatever is broken atm
from spock.mcp import mcdata

class DebugPlugin:
	def __init__(self, client):
		self.client = client
		for ident in mcdata.structs:
			client.register_dispatch(self.debug, ident)
	def debug(self, packet):
		if (packet.ident == 0xC9 
		or packet.ident == 0x03
		or packet.ident == 0xFF
		or packet.ident == 0x0D):
			print packet
		if packet.ident == 0x0D:
			if packet.direction == mcdata.SERVER_TO_CLIENT:
				packet.direction = mcdata.CLIENT_TO_SERVER
				self.client.push(packet)
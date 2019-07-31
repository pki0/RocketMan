from geopy.distance import great_circle
import matplotlib.path as mplPath
import numpy as np

class DSPokemon:
	def __init__(self, pokestop_id, name, incident_expiration, latitude, longitude, grunt_type):
		self.pokestop_id = pokestop_id
		self.pokestopname = name
		self.incident_expiration = incident_expiration
		self.latitude = latitude
		self.longitude = longitude
		self.grunt_type = grunt_type

	def getPokestopID(self):
		return self.pokestop_id

	def getPokestopName(self):
		return self.pokestopname

	def getPokestopExpiration(self):
		return self.incident_expiration

	def getLatitude(self):
		return self.latitude

	def getLongitude(self):
		return self.longitude

	def getGruntType(self):
		return self.grunt_type

	def filterbylocation(self,user_location):
		user_lat_lon = (user_location[0], user_location[1])
		pok_loc = (float(self.latitude), float(self.longitude))
		return great_circle(user_lat_lon, pok_loc).km <= user_location[2]

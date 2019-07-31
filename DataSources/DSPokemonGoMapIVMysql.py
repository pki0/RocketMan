from .DSPokemon import DSPokemon

import os
from datetime import datetime
import logging

import pymysql
import re

logger = logging.getLogger(__name__)

class DSPokemonGoMapIVMysql():
	def __init__(self, connectString):
		# open the database
		sql_pattern = 'mysql://(.*?):(.*?)@(.*?):(\d*)/(\S+)'
		(user, passw, host, port, db) = re.compile(sql_pattern).findall(connectString)[0]
		self.__user = user
		self.__passw = passw
		self.__host = host
		self.__port = int(port)
		self.__db = db
		logger.info('Connecting to remote database')
		self.__connect()

	def getPokemonData(self):
		pokelist = []

		sqlquery = "SELECT pokestop_id, name, incident_expiration, latitude, longitude, incident_grunt_type"
		sqlquery += ' FROM pokestop'
		sqlquery += ' WHERE incident_expiration > UTC_TIMESTAMP() '

		try:
			with self.con:
				cur = self.con.cursor()

				cur.execute(sqlquery)
				rows = cur.fetchall()
				for row in rows:
					pokestop_id = str(row[0])
					name = str(row[1])
					incident_expiration = datetime.strptime(str(row[2])[0:19], "%Y-%m-%d %H:%M:%S")
					latitude = str(row[3])
					longitude = str(row[4])
					grunt_type = str(row[5])

					poke = DSPokemon(pokestop_id, name, incident_expiration, latitude, longitude, grunt_type)
					pokelist.append(poke)
		except pymysql.err.OperationalError as e:
			if e.args[0] == 2006:
				self.__reconnect()
			else:
				logger.error(e)
		except Exception as e:
			logger.error(e)

		return pokelist


	def __connect(self):
		self.con = pymysql.connect(user=self.__user,password=self.__passw,host=self.__host,port=self.__port,database=self.__db, charset='utf8')

	def __reconnect(self):
		logger.info('Reconnecting to remote database')
		self.__connect()

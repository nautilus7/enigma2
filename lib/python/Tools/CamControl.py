from os import listdir, readlink, symlink, unlink
from os.path import exists, split

import enigma


class CamControl:
	"""CAM convention is that a softlink named /etc/init.c/softcam.* points
	to the start/stop script."""

	def __init__(self, name):
		self.name = name
		self.link = "/etc/init.d/%s" % name
		if not exists(self.link):
			print("[CamControl] Not a softcam link: %s" % self.link)

	def getList(self):
		result = []
		prefix = ".%s" % self.name
		for f in listdir("/etc/init.d"):
			if f.startswith(prefix):
				result.append(f[len(prefix):])
		return result

	def current(self):
		try:
			l = readlink(self.link)
			prefix = ".%s" % self.name
			return split(l)[1].split(prefix, 2)[1]
		except:
			pass
		return None

	def command(self, cmd):
		if exists(self.link):
			print("[CamControl] Executing %s %s" % (self.link, cmd))
			enigma.eConsoleAppContainer().execute("%s %s" % (self.link, cmd))

	def select(self, softcam):
		print("[CamControl] Selecting softcam %s" % softcam)
		if not softcam:
			softcam = "None"
		dst = "%s.%s" % (self.name, softcam)
		if not exists("/etc/init.d/%s" % dst):
			print("[CamControl] Init script does not exist: %s" % dst)
			return
		try:
			unlink(self.link)
		except:
			pass
		try:
			symlink(dst, self.link)
		except:
			print("[CamControl] Failed to create symlink for softcam: %s" % dst)
			import sys
			print(sys.exc_info()[:2])

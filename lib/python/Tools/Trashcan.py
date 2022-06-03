from os import W_OK, access, mkdir, rmdir, stat, statvfs, walk
from os.path import getsize, isdir, join as pathjoin, realpath, split
from time import time
from twisted.internet import threads

from Components.config import config
from Components.GUIComponent import GUIComponent
from Components.Harddisk import findMountPoint, getProcMounts
from Components.Task import Job, PythonTask
from Components.VariableText import VariableText

from enigma import eBackgroundFileEraser, eLabel, iRecordableService, pNavigation


def getTrashFolder(path=None):  # Returns trash folder without symlinks
	try:
		if path is None or realpath(path) == "/media/autofs":
			print("[Trashcan] path is none")
			return ""
		else:
			trashcan = findMountPoint(realpath(path))
			if "/movie" in path:
				trashcan = pathjoin(trashcan, "movie")
			elif config.usage.default_path.value in path:
				# if default_path happens to not be the default /hdd/media/movie, then we can have a trash folder there instead
				trashcan = pathjoin(trashcan, config.usage.default_path.value)
			return realpath(pathjoin(trashcan, ".Trash"))
	except:
		return None


def createTrashFolder(path=None):
	trash = getTrashFolder(path)
	if trash and access(split(trash)[0], W_OK):
		if not isdir(trash):
			try:
				mkdir(trash)
			except:
				return None
		return trash
	else:
		return None


def get_size(start_path="."):
	total_size = 0
	if start_path:
		for dirpath, dirnames, filenames in walk(start_path):
			for f in filenames:
				try:
					fp = pathjoin(dirpath, f)
					total_size += getsize(fp)
				except:
					pass
	return total_size


def enumTrashFolders():
	# Walk through all Trash folders. This may access network
	# drives and similar, so might block for minutes.
	for mount in getProcMounts():
		if mount[1].startswith("/media/"):
			mountpoint = mount[1]
			movie = pathjoin(mountpoint, "movie")
			if isdir(movie):
				mountpoint = movie
			result = pathjoin(mountpoint, ".Trash")
			if isdir(result):
				yield result


class Trashcan:
	def __init__(self, session):
		self.session = session
		self.isCleaning = False
		self.dirty = set()
		self.session.nav.record_event.append(self.gotRecordEvent)

	def markDirty(self, path=""):
		# Marks a path for purging, for when a recording on that
		# device starts or ends.
		if path:
			trash = getTrashFolder(path)
			self.dirty.add(trash)

	def gotRecordEvent(self, event):
		from RecordTimer import n_recordings
		if event == iRecordableService.evEnd:
			self.cleanIfIdle()

	def destroy(self):
		if self.session is not None:
			self.session.nav.record_event.remove(self.gotRecordEvent)
		self.session = None

	def __del__(self):
		self.destroy()

	def cleanIfIdle(self, path=None):
		# RecordTimer calls this when preparing a recording. That is a
		# nice moment to clean up. It also mentions the path, so mark
		# it as dirty.
		from RecordTimer import n_recordings
		if n_recordings > 0:
			print("[Trashcan] Recording(s) in progress:", n_recordings)
			return
		self.markDirty(path)
		if not self.dirty:
			return
		if self.isCleaning:
			print("[Trashcan] Cleanup already running.")
			return
		if self.session is not None and self.session.nav.getRecordings():
			return
		self.isCleaning = True
		ctimeLimit = time.time() - (config.usage.movielist_trashcan_days.value * 3600 * 24)
		reserveBytes = 1024 * 1024 * 1024 * int(config.usage.movielist_trashcan_reserve.value)
		cleanset = self.dirty
		self.dirty = set()
		threads.deferToThread(purge, cleanset, ctimeLimit, reserveBytes).addCallbacks(self.cleanReady, self.cleanFail)

	def cleanReady(self, result=None):
		self.isCleaning = False
		# schedule another clean loop if needed (so we clean up all devices, not just one)
		self.cleanIfIdle()

	def cleanFail(self, failure):
		print("[Trashcan] ERROR in clean: %s" % failure)
		self.isCleaning = False


def purge(cleanset, ctimeLimit, reserveBytes):
	# Remove expired items from trash, and attempt to have
	# reserveBytes of free disk space.
	for trash in cleanset:
		if not isdir(trash):
			print("[Trashcan] No trash.", trash)
			return 0
		diskstat = statvfs(trash)
		free = diskstat.f_bfree * diskstat.f_bsize
		bytesToRemove = reserveBytes - free
		candidates = []
		print("[Trashcan] bytesToRemove", bytesToRemove, trash)
		size = 0
		for root, dirs, files in walk(trash, topdown=False):
			for name in files:
				try:
					fn = pathjoin(root, name)
					st = stat(fn)
					if st.st_ctime < ctimeLimit:
						print("[Trashcan] Too old:", name, st.st_ctime)
						eBackgroundFileEraser.getInstance().erase(fn)
						bytesToRemove -= st.st_size
					else:
						candidates.append((st.st_ctime, fn, st.st_size))
						size += st.st_size
				except Exception as e:
					print("[Trashcan] Failed to stat %s:" % name, e)
			# Remove empty directories if possible
			for name in dirs:
				try:
					rmdir(pathjoin(root, name))
				except:
					pass
		candidates.sort()
		# Now we have a list of ctime, candidates, size. Sorted by ctime (=deletion time)
		print("[Trashcan] Bytes to remove remaining:", bytesToRemove, trash)
		for st_ctime, fn, st_size in candidates:
			if bytesToRemove < 0:
				break
			eBackgroundFileEraser.getInstance().erase(fn)
			bytesToRemove -= st_size
			size -= st_size
		print("[Trashcan] Size after purging:", size, trash)


def cleanAll(trash):
	if not isdir(trash):
		print("[Trashcan] No trash.", trash)
		return 0
	for root, dirs, files in walk(trash, topdown=False):
		for name in files:
			fn = pathjoin(root, name)
			try:
				eBackgroundFileEraser.getInstance().erase(fn)
			except Exception as e:
				print("[Trashcan] Failed to erase %s: " % name, e)
		# Remove empty directories if possible
		for name in dirs:
			try:
				rmdir(pathjoin(root, name))
			except:
				pass


TrashcanInstance = None


def InitTrashcan(session):
	global TrashcanInstance
	if TrashcanInstance is None:
		TrashcanInstance = Trashcan(session)


class CleanTrashTask(PythonTask):
	def openFiles(self, ctimeLimit, reserveBytes):
		self.ctimeLimit = ctimeLimit
		self.reserveBytes = reserveBytes

	def work(self):
		mounts = []
		matches = []
		print("[Trashcan] Probing folders.")
		with open("/proc/mounts", "r") as mountsPoints:
			for mountPoint in mountsPoints.readlines():
				parts = mountPoint.strip().split()
				if parts[1] == "/media/autofs":
					continue
				if config.usage.movielist_trashcan_network_clean.value and parts[1].startswith("/media/net"):
					mounts.append(parts[1])
				elif config.usage.movielist_trashcan_network_clean.value and parts[1].startswith("/media/autofs"):
					mounts.append(parts[1])
				elif not parts[1].startswith("/media/net") and not parts[1].startswith("/media/autofs"):
					mounts.append(parts[1])
		for mount in mounts:
			if isdir(pathjoin(mount, ".Trash")):
				matches.append(pathjoin(mount, ".Trash"))
			if isdir(pathjoin(mount, "movie/.Trash")):
				matches.append(pathjoin(mount, "movie/.Trash"))
		print("[Trashcan] Found the following trashcans: %s" % matches)
		if len(matches):
			for trashfolder in matches:
				print("[Trashcan] Looking in trashcan %s." % trashfolder)
				trashsize = get_size(trashfolder)
				diskstat = statvfs(trashfolder)
				free = diskstat.f_bfree * diskstat.f_bsize
				bytesToRemove = self.reserveBytes - free
				print("[Trashcan] %s: Size %s." % (str(trashfolder),  trashsize))
				candidates = []
				size = 0
				for root, dirs, files in walk(trashfolder, topdown=False):
					for name in files:
						# Don't delete any per-directory config files from .Trash if the option is in use
						if config.movielist.settings_per_directory.value and name == ".e2settings.pkl":
							continue
						try:
							fn = pathjoin(root, name)
							st = stat(fn)
							if st.st_ctime < self.ctimeLimit:
								eBackgroundFileEraser.getInstance().erase(fn)
								bytesToRemove -= st.st_size
							else:
								candidates.append((st.st_ctime, fn, st.st_size))
								size += st.st_size
						except Exception as e:
							print("[Trashcan] Failed to stat %s: %s" % name, e)
					# Remove empty directories if possible
					for name in dirs:
						try:
							rmdir(pathjoin(root, name))
						except:
							pass
					candidates.sort()
					# Now we have a list of ctime, candidates, size. Sorted by ctime (=deletion time)
					for st_ctime, fn, st_size in candidates:
						if bytesToRemove < 0:
							break
						try:
							# Sometimes the file does not exist. This can happen if trashcan is on a network,
							# the main box could also be emptying trash at same time.
							eBackgroundFileEraser.getInstance().erase(fn)
						except:
							pass
						bytesToRemove -= st_size
						size -= st_size
					print("[Trashcan] %s: Size now %s." % (str(trashfolder), size))


class TrashInfo(VariableText, GUIComponent):
	FREE = 0
	USED = 1
	SIZE = 2

	def __init__(self, path, type, update=True):
		GUIComponent.__init__(self)
		VariableText.__init__(self)
		self.type = type
		if update and path != "/media/autofs/":
			self.update(path)

	def update(self, path):
		try:
			total_size = get_size(getTrashFolder(path))
		except OSError:
			return -1

		if self.type == self.USED:
			try:
				if total_size < 10000000:
					total_size = _("%d KB") % (total_size >> 10)
				elif total_size < 10000000000:
					total_size = _("%d MB") % (total_size >> 20)
				else:
					total_size = _("%d GB") % (total_size >> 30)
				self.setText(_("Trashcan: %s") % total_size)
			except:
				# occurs when f_blocks is 0 or a similar error
				self.setText("-?-")

	GUI_WIDGET = eLabel

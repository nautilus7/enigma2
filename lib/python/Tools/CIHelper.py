from os import remove
from os.path import exists
from xml.etree.ElementTree import parse

import NavigationInstance
from Components.config import config
from Components.SystemInfo import SystemInfo

from enigma import eDVBCI_UI, eDVBCIInterfaces, eEnv, eServiceCenter, eServiceReference, getBestPlayableServiceReference, iRecordableService


class CIHelper:

	CI_ASSIGNMENT_LIST = None
	CI_ASSIGNMENT_SERVICES_LIST = None
	CI_MULTIDESCRAMBLE = None
	CI_RECORDS_LIST = None
	CI_INIT_NOTIFIER = None
	CI_MULTIDESCRAMBLE_MODULES = ("AlphaCrypt", "M7 CAM701 Multi-2")

	def parseCiAssignment(self):
		NUM_CI = SystemInfo["CommonInterface"]
		if NUM_CI and NUM_CI > 0:
			self.CI_ASSIGNMENT_LIST = []

			def getValue(definitions, default):
				length = len(definitions)
				return definitions[length - 1].text if length > 0 else default

			for ci in range(NUM_CI):
				filename = eEnv.resolve("${sysconfdir}/enigma2/ci%d.xml" % ci)
				if not exists(filename):
					continue
				try:
					tree = parse(filename).getroot()
					readServices = []
					readProviders = []
					activeCaid = []
					for slot in tree.findall("slot"):
						readSlot = getValue(slot.findall("id"), False)
						if readSlot and self.CI_ASSIGNMENT_SERVICES_LIST is None:
							self.CI_ASSIGNMENT_SERVICES_LIST = {}
						for caid in slot.findall("caid"):
							readCaid = caid.get("id", "0")
							activeCaid.append(int(readCaid, 16))
						for service in slot.findall("service"):
							readServiceRef = service.get("ref")
							readServices.append(readServiceRef)
							if readSlot and self.CI_ASSIGNMENT_SERVICES_LIST and not self.CI_ASSIGNMENT_SERVICES_LIST.get(readServiceRef, False):
								self.CI_ASSIGNMENT_SERVICES_LIST[readServiceRef] = readSlot
						for provider in slot.findall("provider"):
							readProviderName = provider.get("name")
							readProviderDvbnamespace = provider.get("dvbnamespace", "0")
							readProviders.append((readProviderName, int(readProviderDvbnamespace, 16)))
							if readSlot:
								provider_services_refs = self.getProviderServices([readProviderName])
								if provider_services_refs:
									for ref in provider_services_refs:
										if not self.CI_ASSIGNMENT_SERVICES_LIST.get(ref, False):
											self.CI_ASSIGNMENT_SERVICES_LIST[ref] = readSlot
						if readSlot:
							self.CI_ASSIGNMENT_LIST.append((int(readSlot), (readServices, readProviders, activeCaid)))
				except:
					print("[CI_ASSIGNMENT %d] ERROR parsing xml..." % ci)
					try:
						remove(filename)
					except:
						print("[CI_ASSIGNMENT %d] ERROR removing damaged xml..." % ci)
			if self.CI_ASSIGNMENT_LIST:
				for item in self.CI_ASSIGNMENT_LIST:
					try:
						eDVBCIInterfaces.getInstance().setDescrambleRules(item[0], item[1])
						print("[CI_ASSIGNMENT %d] Activating with following settings." % item[0])
					except:
						print("[CI_ASSIGNMENT %d] ERROR setting descrambling rules." % item[0])

	def ciRecordEvent(self, service, event):
		if event in (iRecordableService.evEnd, iRecordableService.evStart, None):
			self.CI_RECORDS_LIST = []
			if NavigationInstance.instance.getRecordings() and hasattr(NavigationInstance.instance, "RecordTimer") and hasattr(NavigationInstance.instance.RecordTimer, "timer_list"):
				for timer in NavigationInstance.instance.RecordTimer.timer_list:
					if not timer.justplay and timer.state in (1, 2) and timer.record_service and not (timer.record_ecm and not timer.descramble):
						if timer.service_ref.ref.flags & eServiceReference.isGroup:
							timerService = hasattr(timer, "rec_ref") and timer.rec_ref
							if not timerService:
								timerService = getBestPlayableServiceReference(timer.service_ref.ref, eServiceReference())
						else:
							timerService = timer.service_ref.ref
						if timerService:
							isAssignment = self.serviceIsAssigned(timerService.toString())
							if isAssignment:
								if isAssignment[0] not in self.CI_RECORDS_LIST:
									self.CI_RECORDS_LIST.insert(0, isAssignment[0])
								if isAssignment not in self.CI_RECORDS_LIST:
									self.CI_RECORDS_LIST.append(isAssignment)

	def loadCiAssignment(self, force=False):
		if self.CI_ASSIGNMENT_LIST is None or force:
			self.parseCiAssignment()

	def getProviderServices(self, providers):
		providerServicesRefs = []
		if len(providers):
			serviceHandler = eServiceCenter.getInstance()
			for x in providers:
				refStr = '1:7:0:0:0:0:0:0:0:0:(provider == "%s") && (type == 1) || (type == 17) || (type == 22) || (type == 25) || (type == 31) || (type == 134) || (type == 195) ORDER BY name:%s' % (x, x)
				serviceList = serviceHandler.list(eServiceReference(refStr))
				if serviceList is not None:
					while True:
						service = serviceList.getNext()
						if not service.valid():
							break
						providerServicesRefs.append(service.toString())
		return providerServicesRefs

	def serviceIsAssigned(self, ref, timer=None):
		if self.CI_ASSIGNMENT_SERVICES_LIST is not None:
			if self.CI_RECORDS_LIST is None and NavigationInstance.instance and hasattr(NavigationInstance.instance, "RecordTimer") and hasattr(NavigationInstance.instance, "record_event"):
				NavigationInstance.instance.record_event.append(self.ciRecordEvent)
				self.ciRecordEvent(None, None)
			if ref and ref.startswith("1:134:"):
				if timer:
					if timer.state == 2 and not timer.justplay:
						if hasattr(timer, "rec_ref") and timer.rec_ref:
							ref = timer.rec_ref.toString()
					else:
						alternativeServices = eServiceCenter.getInstance().list(eServiceReference(ref))
						if alternativeServices:
							count = 0
							isCiService = 0
							ciSlot = []
							for service in alternativeServices.getContent("S", True):
								count += 1
								isAssignment = self.CI_ASSIGNMENT_SERVICES_LIST.get(service, False)
								if isAssignment:
									isCiService += 1
									if isAssignment not in ciSlot:
										ciSlot.append(isAssignment)
										if len(ciSlot) > 1:
											return False
							if ciSlot and count == isCiService:
								return (ciSlot[0], "")
						return False
				else:
					return False
			if ref:
				isAssignment = self.CI_ASSIGNMENT_SERVICES_LIST.get(ref, False)
				return isAssignment and (isAssignment, ref) or False
		return False

	def forceUpdateMultiDescramble(self, configElement):
		self.CI_MULTIDESCRAMBLE = None

	def canMultiDescramble(self, ci):
		if self.CI_MULTIDESCRAMBLE is None:
			ciCount = SystemInfo["CommonInterface"]
			if ciCount and ciCount > 0:
				self.CI_MULTIDESCRAMBLE = []
				for slot in range(ciCount):
					appName = eDVBCI_UI.getInstance().getAppName(slot)
					multipleServices = config.ci[slot].canDescrambleMultipleServices.value
					if self.CI_INIT_NOTIFIER is None:
						config.ci[slot].canDescrambleMultipleServices.addNotifier(self.forceUpdateMultiDescramble, initial_call=False, immediate_feedback=False)
					if multipleServices == "yes" or (appName in self.CI_MULTIDESCRAMBLE_MODULES and multipleServices == "auto"):
						self.CI_MULTIDESCRAMBLE.append(str(slot))
				self.CI_INIT_NOTIFIER = True
		else:
			return self.CI_MULTIDESCRAMBLE and ci in self.CI_MULTIDESCRAMBLE

	def isPlayable(self, service):
		isAssignment = self.serviceIsAssigned(service)
		if isAssignment and self.CI_RECORDS_LIST and isAssignment[0] in self.CI_RECORDS_LIST and isAssignment not in self.CI_RECORDS_LIST:
			if self.canMultiDescramble(isAssignment[0]):
				for timerService in self.CI_RECORDS_LIST:
					if len(timerService) > 1:
						if timerService[0] == isAssignment[0]:
							eService = eServiceReference(timerService[1])
							eService1 = eServiceReference(service)
							for x in (4, 2, 3):
								if eService.getUnsignedData(x) != eService1.getUnsignedData(x):
									return 0
			else:
				return 0
		return 1


cihelper = CIHelper()


def isPlayable(service):
	return cihelper.isPlayable(service)

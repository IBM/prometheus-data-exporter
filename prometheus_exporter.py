#!/usr/bin/env python3

import time
import requests
import sys
import logging
import urllib3
import argparse
import json
import re
import xlsxwriter
import os
import textwrap
import ast
import gc
from pathlib import Path
from os import path
from datetime import datetime
from calendar import timegm
try:
	import psutil
except ImportError:
	print("Warning: Failed to import psutil, will not have memory details.")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
script_version = "5.0.2 20211213"

#Initialize
def init():
	#formatter = lambda prog: argparse.HelpFormatter(prog,max_help_position=12)
	#formatter_class=formatter,
	global parser
	parser = argparse.ArgumentParser( prog='prometheus_exporter.py', description=textwrap.dedent('''\
	https://github.ibm.com/katamari/katamari-performance/wiki/Prometheus-Data-Exporter-and-Analyzer
	Prometheus Data Exporter. Used for exporting and analyzing historical Prometheus data.
	Specifically focusing on Kubernetes deployments.
	'''), 
	epilog=textwrap.dedent('''\
	Example: 
	--tknfile S:/temp/token --url https://prometheus-k8s-openshift-monitoring.apps.cp4mcmperf11.cp.fyre.ibm.com --start=20210429140000 --end=20210429143000 --filename test42 --dir /promTestAnalysis --n "cp4waiops" --regex ".*kafka.*" --loglevel prog --keyReport'''))
	#parser._action_groups.pop()
	global metricParser
	metricParser = parser.add_argument_group('METRIC arguments')
	global groupingParser
	groupingParser = parser.add_argument_group('GROUPING arguments')
	global regexParser
	regexParser = parser.add_argument_group('REGEX arguments')
	global keyParser
	keyParser = parser.add_argument_group('KEY arguments')
	global requiredParser
	requiredParser = parser.add_argument_group('REQUIRED arguments')
	setupParser()
	global arg 
	arg = parser.parse_args()
	global configDictionary
	configDictionary = {}
	global newPrometheus
	newPrometheus = True
	setupLogging()

	global inPodRegexList
	inPodRegexList = list(arg.regex.split(" "))
	global inPodNRegexList
	inPodNRegexList = list(arg.nregex.split(" "))
	
	global workloadMergeLists
	workloadMergeLists = {}
	workloadMergeLists["cp4waiops"] = ["learner-.*", "jobmonitor-.*"]
	workloadMergeLists["aiops"] = ["learner-.*", "jobmonitor-.*"]
	
	logging.prog("Script version: " + script_version)
	
	global queryDictionary
	queryDictionary = {}
	defineQueryDictionary()
	global namesForReqLim
	namesForReqLim = ["cpuReq", "cpuLim", "memReq", "memLim"]
	global namesForSummary
	namesForSummary = ["container_detail", "pod_detail", "pod_sum", "container_sum", "namespace", "nodes", "pv"] #"filesystem", "disk"
	global groupsForReqLimAll
	groupsForReqLimAll = ["namespace", "nodes"]

	global url
	url = arg.url
	logging.debug("url: " + str(url))
	global token 
	token = getToken()
	
	global startQueryTime 
	startQueryTime = convertDateToPromFormat(arg.start)
	global start_epoch 
	if startQueryTime:
		start_epoch = convertDateToEpoch(arg.start)
	global endQueryTime 
	endQueryTime = convertDateToPromFormat(arg.end)
	global end_epoch
	if endQueryTime: 
		end_epoch = convertDateToEpoch(arg.end)
	logging.debug("startQueryTime: " + str(start_epoch) + " " + startQueryTime) 
	logging.debug("  endQueryTime: " + str(end_epoch) + " " + endQueryTime) 
	
	
	global step 
	step = arg.step
	global step_int 
	step_int = int(re.sub("[^0-9]", "", arg.step))
	logging.debug("step_int: " + str(step_int))
def initNamespace(namespace):

	global workbook	 
	workbook = {}
	global worksheets
	worksheets = {}
	global worksheetsCounter
	worksheetsCounter = {}
	global textWrap
	textWrap = {}
	global itemTitle
	itemTitle = {}
	
	global decimalFormat
	decimalFormat = {}
	global integerFormat
	integerFormat = {}
	global percentFormat
	percentFormat = {}	
	
	global metricDataDictionary 
	metricDataDictionary = {}
	global metricDataSummaryDictionary
	metricDataSummaryDictionary = {}

def getPodRegexList(namespace, index, groupingType):
	templist = list()
	#Add input argument regex
	inRegex = ""
	if ( index >= 0 and index < len(inPodRegexList) ):
		inRegex = inPodRegexList[index]	
	
	if ("_sum" in groupingType) or ("_avg" in groupingType):
		if inRegex == "" or inRegex == '.*':
			logging.more(" getPodRegexList regex empty, adding .*")
			inRegex = ".*"
			templist.append(inRegex)	
			if namespace in workloadMergeLists:
				logging.more(" getPodRegexList namespace is special, adding all merges")
				for regex in workloadMergeLists[namespace]:
					templist.append(regex)
			else:
				logging.more(" getPodRegexList namespace is not special, not adding all merges")
		else:
			logging.more(" getPodRegexList regex has value " + inRegex)
			templist.append(inRegex)	
			if namespace in workloadMergeLists: 
				logging.more(" getPodRegexList namespace is special")
				if inRegex in workloadMergeLists[namespace]:
					logging.more(" getPodRegexList inRegex " + inRegex + " is in merge list " + str(workloadMergeLists[namespace]) + " adding it again")
					templist.append(inRegex)
				else:
					logging.more(" getPodRegexList inRegex " + inRegex + " is NOT in merge list " + str(workloadMergeLists[namespace]))	
			else:
				logging.more(" getPodRegexList namespace is not special")
	else:	
		if inRegex == "":
			logging.more(" getPodRegexList regex empty, adding .*")
			inRegex = ".*"
		logging.more(" getPodRegexList details \"" + inRegex + "\"")
		templist.append(inRegex)
	return templist	
def getNPodRegexList(namespace, index, groupingType):
	templist = list()	
	inNRegex = ""
	if ( index >= 0 and index < len(inPodNRegexList) ):
		inNRegex = inPodNRegexList[index]	
	
	if ("_sum" in groupingType) or ("_avg" in groupingType):
		inRegex = ""
		if ( index >= 0 and index < len(inPodRegexList) ):
			inRegex = inPodRegexList[index]	
		if inRegex == "" or inRegex == '.*': 
			logging.more(" getNPodRegexList regex empty, adding all")
			if namespace in workloadMergeLists:
				logging.more(" getNPodRegexList namespace has special, adding all")
				nregex = inNRegex
				for entry in workloadMergeLists[namespace]:
					nregex = nregex + "|" + entry
				logging.more(" getNPodRegexList built special nregex list: " + str(nregex))
				templist.append(nregex)
				for regex in workloadMergeLists[namespace]:
					templist.append("")
			else:
				logging.more(" getNPodRegexList Not a special namespace, just adding the inNRegex " + inNRegex)
				templist.append(inNRegex)	
		else:
			logging.more(" getNPodRegexList regex has value " + inRegex)
			if namespace in workloadMergeLists: 
				logging.more(" getNPodRegexList namespace has special")
				if inRegex in workloadMergeLists[namespace]:
					logging.more(" getPodRegexList inRegex " + inRegex + " is in merge list " + str(workloadMergeLists[namespace]) + " adding inNRegex again")
					templist.append(inRegex)
					templist.append(inNRegex)
				else:
					logging.more(" getPodRegexList inRegex " + inRegex + " is NOT merge list " + str(workloadMergeLists[namespace]) + " adding inNRegex again")
					templist.append(inNRegex)					
			else:	
				logging.more(" getNPodRegexList namespace is not special")
				templist.append(inNRegex)	
	else:
		logging.more(" getNPodRegexList details \"" + inNRegex + "\"")
		templist.append(inNRegex)
	return templist
def setupParser():
	parser.add_argument(
		"--retain", 
		action='store_true',
		help=("Keep the raw data around in the metric dictionary, even after writing to Excel. Will use more memory since data is normally cleared once finished with.")
	)
	keyParser.add_argument(
		"--loglevel", 
		default="info",
		help=("Logging level: critical, error, warn, warning, info, prog, more, debug, verbose.  Default is info.")
	)
	keyParser.add_argument(
		"--csv", 
		action='store_true',
		help=("Also output data as csv format, in addition to default xlsx")
	)
	keyParser.add_argument(
		"--dir", 
		help=("Directory to store the results in")
	)
	keyParser.add_argument(
		"--filename", 
		help=("Additional string to add to output filename")
	)
	keyParser.add_argument(
		"--cfgFile", 
		help=("Filename of the dictionary of dictionaries with analysis configuration.  If not specified, will look for prometheus_exporter_config.json and then config.json.  If not found, default settings internal to the script are used.")
	)
	keyParser.add_argument(
		"--step",
		default="30",
		help=("Step (in seconds only) for range query, default is 30")
	)
	keyParser.add_argument(
		"--printSummary", 
		action='store_true',
		help=("Print the summary data to screen.")
	)
	keyParser.add_argument(
		"--printAnalysis", 
		action='store_true',
		help=("Print the analysis of the data to screen.")
	)
	keyParser.add_argument(
		"--workload", 
		action='store_true',
		help=("Details on the workload being run.")
	)
	#Report
	keyParser.add_argument(
		"--keyReport",
		action='store_true',
		help=("Return all key data (pod and container details and summary, namespaces, nodes, filesystems; uses keyMetrics)")
	)
	keyParser.add_argument(
		"--report",
		action='store_true',
		help=("Return all known data")
	)
	#Required
	requiredParser.add_argument(
		"--n",
		"--namespace",
		#action='append',
		#default=[],
		dest='namespace',
		help=("Namespace to gather detailed data for"),
		required=True
	)
	requiredParser.add_argument(
		"--url",
		help=("URL of the prometheus server"),
		required=True
	)
	requiredParser.add_argument(
		"--tknfile",
		help=("File with the token in it (either this or the token string --token are required)"),
		required=True
	)
	requiredParser.add_argument(
		"--start",
		help=("Start time for range query in UTC, format 20210514180000 or 2021-05-14T18:00:00 or 2021-05-14T18:00:00.000Z"),
		required=True
	)
	requiredParser.add_argument(
		"--end",
		help=("End time for range query in UTC, format 20210514180000 or 2021-05-14T18:00:00 or 2021-05-14T18:00:00.000Z"),
		required=True
	)
	#Metrics
	metricParser.add_argument(
		"--rate",
		default="5m",
		help=("Step for range query, default is 5m")
	)
	metricParser.add_argument(
		"--cpu",
		action='store_true',
		help=("Return total CPU usage data using the pre-rated metric")
	)
	metricParser.add_argument(
		"--cpur",
		action='store_true',
		help=("Return total CPU usage data using the custom rate")
	)
	metricParser.add_argument(
		"--cpuUser",
		action='store_true',
		help=("Return CPU user usage data")
	)
	metricParser.add_argument(
		"--cpuSys",
		action='store_true',
		help=("Return CPU system usage data")
	)
	metricParser.add_argument(
		"--throttle",
		action='store_true',
		help=("Return CPU throttle data")
	)
	metricParser.add_argument(
		"--allCpu",
		action='store_true',
		help=("Return data for all CPU metrics")
	)
	metricParser.add_argument(
		"--rss",
		action='store_true',
		help=("Return RSS memory data")
	)
	metricParser.add_argument(
		"--wss",
		action='store_true',
		help=("Return WSS memory data")
	)
	metricParser.add_argument(
		"--cache",
		action='store_true',
		help=("Return cache memory data")
	)
	metricParser.add_argument(
		"--mmap",
		action='store_true',
		help=("Return mapped memory data")
	)
	metricParser.add_argument(
		"--memUse",
		action='store_true',
		help=("Return total memory usage data")
	)
	metricParser.add_argument(
		"--allMem",
		action='store_true',
		help=("Return data for all memory metrics")
	)
	metricParser.add_argument(
		"--reqlim",
		action='store_true',
		help=("Return data for requests and limits")
	)
	metricParser.add_argument(
		"--network",
		action='store_true',
		help=("Return data for network usage (not available at container level)")
	)
	metricParser.add_argument(
		"--probes",
		action='store_true',
		help=("Return data for probes, restarts, liveness, etc.")
	)
	metricParser.add_argument(
		"--keyMetrics",
		action='store_true',
		help=("Return data for all key metrics (count, req/lim, CPUr, RSS, WSS, Cache, memUse, RX/TX)")
	)
	metricParser.add_argument(
		"--allMetrics",
		action='store_true',
		help=("Return data for all known metrics")
	)
	#Grouping
	groupingParser.add_argument(
		"--namespaceTotals",
		action='store_true',
		help=("Display details at the namespace level")
	)
	groupingParser.add_argument(
		"--nodes",
		action='store_true',
		help=("Display node details")
	)
	groupingParser.add_argument(
		"--disk",
		action='store_true',
		help=("Display disk details")
	)
	groupingParser.add_argument(
		"--filesystem",
		action='store_true',
		help=("Display filesystem details")
	)
	groupingParser.add_argument(
		"--pv",
		action='store_true',
		help=("Display persistent volume details")
	)
	groupingParser.add_argument(
		"--cluster",
		action='store_true',
		help=("Display details at the cluster (namespaceTotals, nodes, disk, filesystem, pvs)")
	)
	groupingParser.add_argument(
		"--pod",
		action='store_true',
		help=("Display pod level details")
	)
	groupingParser.add_argument(
		"--container",
		action='store_true',
		help=("Display container level details")
	)
	groupingParser.add_argument(
		"--sum",
		action='store_true',
		help=("Sum the details into a single result set by category")
	)
	groupingParser.add_argument(
		"--avg",
		action='store_true',
		help=("Average the details into a single result set by category")
	)
	groupingParser.add_argument(
		"--noDetail",
		action='store_true',
		help=("Do not display the detailed breakdown")
	)
	#Regex
	regexParser.add_argument(
		"--regex",
		default=".*",
		#default=[".*"],
		#type=list,
		#action='append',
		help=("Regex for pod(s) to include, default is all or \".*\"")
	)
	regexParser.add_argument(
		"--nregex",
		default="",
		help=("Negative Regex for pod(s) to exclude, default is no exclusions")
	)
def setupLogging():
	logging.PROG = 19
	logging.addLevelName(logging.PROG, "PROG")
	logging.Logger.prog = lambda inst, msg, *args, **kwargs: inst.log(logging.PROG, msg, *args, **kwargs)
	logging.prog = lambda msg, *args, **kwargs: logging.log(logging.PROG, msg, *args, **kwargs)
	
	logging.MORE = 15
	logging.addLevelName(logging.MORE, "MORE")
	logging.Logger.more = lambda inst, msg, *args, **kwargs: inst.log(logging.MORE, msg, *args, **kwargs)
	logging.more = lambda msg, *args, **kwargs: logging.log(logging.MORE, msg, *args, **kwargs)
	
	logging.VERBOSE = 5
	logging.addLevelName(logging.VERBOSE, "VERBOSE")
	logging.Logger.verbose = lambda inst, msg, *args, **kwargs: inst.log(logging.VERBOSE, msg, *args, **kwargs)
	logging.verbose = lambda msg, *args, **kwargs: logging.log(logging.VERBOSE, msg, *args, **kwargs)
	
	levels = {
		'critical': logging.CRITICAL,
		'error': logging.ERROR,
		'warn': logging.WARNING,
		'warning': logging.WARNING,
		'info': logging.INFO,
		'prog': logging.PROG,
		'more': logging.MORE,
		'debug': logging.DEBUG,
		'verbose': logging.VERBOSE
	}
	level = levels.get(arg.loglevel.lower())
	logging.basicConfig(stream=sys.stdout, level=level, format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
	#logger = logging.getLogger(__name__)
	logging.info("logging level: " + str(level))
def clearData(groupingType, startswithString):
	time.sleep(1)
	logging.prog(getCurrentMemoryUsage() + "clearData start")
	if not arg.retain:
		key_list = generateListOfKeys(metricDataDictionary, startswithString)
		for key in key_list:
			del metricDataDictionary[key] 
			logging.more("clearData key: " + key)
	gc.collect()	
	logging.prog(getCurrentMemoryUsage() + "clearData keys")	
	del workbook[groupingType]
	gc.collect()
	logging.prog(getCurrentMemoryUsage() + "clearData workbook")
	del worksheets[groupingType]
	gc.collect()
	logging.prog(getCurrentMemoryUsage() + "clearData worksheets")	
	return
def printSummaryMessage(message):
	if arg.printSummary:
		print(message)
def printAnalysisMessage(groupingType, metricType, summaryName, thresholdMessage):
	if arg.printAnalysis and thresholdMessage != "":
		message = "{:15} {:60} {:20} {}".format(groupingType, summaryName, metricType, thresholdMessage)
		#print(groupingType + ", " + summaryName + ", \"" + metricType + "\", " + thresholdMessage)
		print(message)

#Helpers
def convertDateToEpoch(inputTime):
	epoch=""
	try:
		epoch = int((datetime.strptime(inputTime, '%Y-%m-%dT%H:%M:%S.%fZ') - datetime(1970, 1, 1)).total_seconds())
	except ValueError:
		try:
			epoch =  int((datetime.strptime(inputTime, '%Y-%m-%dT%H:%M:%S') - datetime(1970, 1, 1)).total_seconds())
		except ValueError:
			try:
				epoch =  int((datetime.strptime(inputTime, '%Y-%m-%dT%H:%M:%SZ') - datetime(1970, 1, 1)).total_seconds())
			except ValueError:
				try:
					epoch =  int((datetime.strptime(inputTime, '%Y%m%d%H%M') - datetime(1970, 1, 1)).total_seconds())
				except ValueError:
					try:
						epoch =  int((datetime.strptime(inputTime, '%Y%m%d%H%M%S') - datetime(1970, 1, 1)).total_seconds())
					except ValueError:
						logging.error("Could not parse time: " + inputTime)
	logging.more("convertDateToEpoch " + inputTime + " -> " + str(epoch))				
	return epoch
def convertDateToInt(inputTime):
	dateAsInt=""
	try:
		dateAsInt = datetime.strptime(inputTime, '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y%m%d%H%M')
	except ValueError:
		try:
			dateAsInt =  datetime.strptime(inputTime, '%Y-%m-%dT%H:%M:%S').strftime('%Y%m%d%H%M')
		except ValueError:
			try:
				dateAsInt =  datetime.strptime(inputTime, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y%m%d%H%M')
			except ValueError:
				try:
					dateAsInt =  datetime.strptime(inputTime, '%Y%m%d%H%M').strftime('%Y%m%d%H%M')
				except ValueError:
					try:
						dateAsInt =  datetime.strptime(inputTime, '%Y%m%d%H%M%S').strftime('%Y%m%d%H%M')
					except ValueError:
						logging.error("Could not parse time: " + inputTime)
	logging.more("convertDateToInt " + inputTime + " -> " + str(dateAsInt))
	return dateAsInt
def convertDateToPromFormat(inputTime):
	dateAsInt=""
	try:
		dateAsInt = datetime.strptime(inputTime, '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%Y-%m-%dT%H:%M:%S.%fZ')
	except ValueError:
		try:
			dateAsInt =  datetime.strptime(inputTime, '%Y-%m-%dT%H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S.%fZ')
		except ValueError:
			try:
				dateAsInt =  datetime.strptime(inputTime, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%dT%H:%M:%S.%fZ')
			except ValueError:
				try:
					dateAsInt =  datetime.strptime(inputTime, '%Y%m%d%H%M').strftime('%Y-%m-%dT%H:%M:%S.%fZ')
				except ValueError:
					try:
						dateAsInt =  datetime.strptime(inputTime, '%Y%m%d%H%M%S').strftime('%Y-%m-%dT%H:%M:%S.%fZ')
					except ValueError:
						logging.error("Could not parse time: " + inputTime)
	logging.more("convertDateToPromFormat " + inputTime + " -> " + str(dateAsInt))
	return dateAsInt
def getToken():
	if arg.tknfile is not None: 
		if path.exists(arg.tknfile):
			logging.debug("tokenfile " + arg.tknfile + " exists")
			file = open(arg.tknfile)
			token = file.read().replace("\n", " ")
			file.close()
			logging.debug("Read token: " + token)
			return token
		else:
			logging.prog("tokenfile does not exist")
	else:
		logging.error("No token found")
		exit(1)
def getConfigDictionary():          
	global configDictionary
	configFilename = arg.cfgFile
	if configFilename is None:
		pathname = os.path.dirname(sys.argv[0])
		configFilename = os.path.abspath(pathname) + "/prometheus_exporter_config.json"
		if os.path.exists(configFilename):
			configFilename = configFilename
		else:
			configFilename = os.path.abspath(pathname) + "/config.json"
	if os.path.exists(configFilename):
		logging.info("Opening configFilename " + configFilename)
		with open(configFilename) as f:
			data = f.read()
		configDictionaryTemp = json.loads(data)
				
		for key1 in configDictionaryTemp:
			logging.more("Config dictionary: " + key1 + " " + str(configDictionaryTemp[key1]))
			configDictionary[key1] = ast.literal_eval(str(configDictionaryTemp[key1]))
	else: 
		logging.info("No file configFilename " + configFilename + " found." )
		#CUSTOMIZE
		configDictionary = {
			"LIST OF ALL":            ['min', 'max', 'avg', 'p25', 'p50', 'p75', 'start', 'end', 'change'],

			"countSummaryList":       ['min', 'max', 'avg'],
			"cpuSummaryList":         ['min', 'max', 'avg', 'p25', 'p50', 'p75', 'start', 'end', 'change'],
			"memSummaryList":         ['min', 'max', 'avg', 'start', 'end', 'change'],
			"netSummaryList":         ['min', 'max', 'avg'],
			"diskSummaryList":        ['min', 'max', 'avg', 'start', 'end', 'change'],
			"fsSummaryList":          ['min', 'max', 'avg', 'start', 'end', 'change'],
			"pvSummaryList":          ['min', 'max', 'avg', 'start', 'end', 'change'],
			"cpuCalcSummaryList":     ['min', 'max', 'avg'],
			"memCalcSummaryList":     ['min', 'max', 'avg'],
			"summaryReqLimList":      ['avg'],
			"summaryReqLimListNodes": ['min', 'max', 'avg'],
			"probeSummaryList": 	  ['max'],

			"#memReq memLim ratio":   {"standard": "50:", "messageLower": "Memory request is significantly below the desired ratio to the limit.", "monitoring-cassandra": "90:"},
			"#memLim memReq diff":    {"standard": ":1000", "messageUpper": "Memory request is significantly below the desired difference from the limit.", "monitoring-cassandra": "1000:"},

			"CPUr cpuReq ratio":      {"standard": "0:100", "messageLower": "CPU usage is significantly below the desired ratio to the request, not enough load?", "messageUpper": "CPU usage is significantly above the allowed ratio to the request, too much load?"},

			"#memUse memLim ratio":   {"standard": "50:90", "messageLower": "Memory usage vs limit ratio is very low, not enough load?",  "messageUpper": "Memory usage vs limit ratio is very high, running low on RAM? Or just kernel cache?"},
			"#memLim memUse diff":    {"standard": "10:200",  "messageLower": "Memory limit minus usage difference is very low, running low on RAM? Or just the kernel cache?", "messageUpper": "Memory limit minus usage difference is very high, not enough load?"},

			"RSS memLim ratio":    {"standard": "5:90", "messageLower": "Memory RSS vs limit ratio is very low, not enough load? Or used by kernel cache?",  "messageUpper": "Memory RSS vs limit ratio is very high, running low on RAM?"},
			"#memLim RSS diff":    {"standard": "50:200",  "messageLower": "Memory limit minus RSS difference is very low, running low on RAM?",  "messageUpper": "Memory limit minus RSS difference is very high, not enough load? Or used by kernel cache?"}
		
		}
	#Debug print
	for key1 in configDictionary:
		logging.more("Config dictionary  key1: " + key1 + " data: " + str(configDictionary[key1]))
def setupXLSX(namespace, groupingType):
	if groupingType not in workbook:
		if startQueryTime and endQueryTime:
			dateRangeString = "." + convertDateToInt(startQueryTime) + "-" + convertDateToInt(endQueryTime)
		else:
			dateRangeString = ""
		if arg.filename:
			filenameExtra = arg.filename + "."
		else:
			filenameExtra = ""
		if namespace:
			namespacePrint = namespace + "."
		else:
			namespacePrint = ""
			
		xlsxFileName = filenameExtra + namespacePrint + groupingType + dateRangeString + ".xlsx"
		
		if arg.dir:
			logging.prog(getCurrentMemoryUsage() + "setupXLSX Creating directory: " + arg.dir)
			Path(arg.dir).mkdir(parents=True, exist_ok=True)
			xlsxFileNameFull = arg.dir + "/" + xlsxFileName
		else:
			xlsxFileNameFull = xlsxFileName
			
		if os.path.exists(xlsxFileName):
			logging.prog("Removing xlsx file: " + xlsxFileName)
			os.remove(xlsxFileName)
			
		logging.info(getCurrentMemoryUsage() + "Adding workbook xlsxFileNameFull: " + xlsxFileNameFull)
		workbook[groupingType] = xlsxwriter.Workbook(xlsxFileNameFull, {'strings_to_numbers': True})
		
		logging.debug("Adding worksheets[" + groupingType + "]")
		worksheets[groupingType] = {}
		worksheetsCounter[groupingType] = {}
		#CUSTOMIZE
		#cpuFormat[groupingType] = workbook[groupingType].add_format({'num_format': '#,##0.000'})
		#memFormat[groupingType] = workbook[groupingType].add_format({'num_format': '#,##0'})
		#netFormat[groupingType] = workbook[groupingType].add_format({'num_format': '#,##0.000'})
		
		textWrap[groupingType] = {}
		itemTitle[groupingType] = {}
		decimalFormat[groupingType] = {}
		integerFormat[groupingType] = {}
		percentFormat[groupingType] = {}
		
		textWrap[groupingType]["standard"] = workbook[groupingType].add_format({'text_wrap': True})
		textWrap[groupingType]["right1_boarder"] = workbook[groupingType].add_format({'text_wrap': True, 'right': 1})
		textWrap[groupingType]["bottom2_boarder"] = workbook[groupingType].add_format({'text_wrap': True, 'bottom': 2})
		textWrap[groupingType]["right1_bottom2_boarder"] = workbook[groupingType].add_format({'text_wrap': True, 'right': 1, 'bottom': 2})
		textWrap[groupingType]["right2_bottom2_boarder"] = workbook[groupingType].add_format({'text_wrap': True, 'right': 2, 'bottom': 2})
		
		itemTitle[groupingType]["right2_boarder"] = workbook[groupingType].add_format({'right': 2})
		
		#decimalFormat[groupingType]["standard"] = workbook[groupingType].add_format({'num_format': '#,##0.000'})
		#integerFormat[groupingType]["standard"] = workbook[groupingType].add_format({'num_format': '#,##0'})
		#percentFormat[groupingType]["standard"] = workbook[groupingType].add_format({'num_format': '0.00%'})
		#decimalFormat[groupingType]["right1_boarder"] = workbook[groupingType].add_format({'num_format': '#,##0.000', 'right': 1})
		#integerFormat[groupingType]["right1_boarder"] = workbook[groupingType].add_format({'num_format': '#,##0', 'right': 1})
		#percentFormat[groupingType]["right1_boarder"] = workbook[groupingType].add_format({'num_format': '0.00%', 'right': 1})
		
		decimalFormat[groupingType]["standard"] = {}
		integerFormat[groupingType]["standard"] = {}
		percentFormat[groupingType]["standard"] = {}
		decimalFormat[groupingType]["right1_boarder"] = {}
		integerFormat[groupingType]["right1_boarder"] = {}
		percentFormat[groupingType]["right1_boarder"] = {}
		
		decimalFormat[groupingType]["standard"]["black"] = workbook[groupingType].add_format({'num_format': '#,##0.000'})
		integerFormat[groupingType]["standard"]["black"] = workbook[groupingType].add_format({'num_format': '#,##0'})
		percentFormat[groupingType]["standard"]["black"] = workbook[groupingType].add_format({'num_format': '0.00%'})
		decimalFormat[groupingType]["right1_boarder"]["black"] = workbook[groupingType].add_format({'num_format': '#,##0.000', 'right': 1})
		integerFormat[groupingType]["right1_boarder"]["black"] = workbook[groupingType].add_format({'num_format': '#,##0', 'right': 1})
		percentFormat[groupingType]["right1_boarder"]["black"] = workbook[groupingType].add_format({'num_format': '0.00%', 'right': 1})
		
		decimalFormat[groupingType]["standard"]["red"] = workbook[groupingType].add_format({'num_format': '#,##0.000', 'font_color': 'red'})
		integerFormat[groupingType]["standard"]["red"] = workbook[groupingType].add_format({'num_format': '#,##0', 'font_color': 'red'})
		percentFormat[groupingType]["standard"]["red"] = workbook[groupingType].add_format({'num_format': '0.00%', 'font_color': 'red'})
		decimalFormat[groupingType]["right1_boarder"]["red"] = workbook[groupingType].add_format({'num_format': '#,##0.000', 'right': 1, 'font_color': 'red'})
		integerFormat[groupingType]["right1_boarder"]["red"] = workbook[groupingType].add_format({'num_format': '#,##0', 'right': 1, 'font_color': 'red'})
		percentFormat[groupingType]["right1_boarder"]["red"] = workbook[groupingType].add_format({'num_format': '0.00%', 'right': 1, 'font_color': 'red'})
	else:
		logging.info("Already had " + groupingType + " in workbook")
def addSheetName(workbookName, sheetName):	
	return workbook[workbookName].add_worksheet(sheetName)
def getCurrentMemoryUsage():	
	try:
		data = "memory(KiB) {:6.0f} - ".format(psutil.Process().memory_info().rss / 1024)
	except NameError:
		data = ""
	return str(data)
def testIterateTimesProcessing(values):
	logging.prog("----------------------------------------------------------------------------------------------------------------------------------------------------------------")
	if logging.VERBOSE >= logging.root.level:
		y = 0		
		for x in range(start_epoch, end_epoch+step_int, step_int):
			timestamp = str(time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(x)))
			logging.verbose("length: " + str(len(values)) + " " + str(y))
			if len(values) > y:
				logging.verbose("compare: " + str(values[y][0]) + " " + str(x))
				if int(values[y][0]) == x: 
					logging.verbose("time: " + timestamp + " " + str(values[y][0]) + " " + str(values[y][1]))
					y+= 1
				else:
					logging.verbose("time: " + timestamp + " missing")
			else:
				logging.verbose("time: " + timestamp + " missing and out of range")	
def testIterateMetricDataDictionary():
	for key in metricDataDictionary:
		logging.debug("key: " + key)
		for name in metricDataDictionary[key]:
			logging.debug("============================================================================")
			logging.debug("key: " + key + "   name: " + str(name))
			dataArray = metricDataDictionary[key][name]
			iteratePrintDataArray(dataArray, "", "", "", "", "", "", "")

#HTTP Functions
def getRequest(url_full, token, params):
	logging.debug("params: " + str(params))
	headers = {"Authorization": "Bearer " + token}
	logging.verbose("headers: " + str(headers))
	response = requests.get(url_full, headers=headers, verify=False, params=params)
	return response
def getMetricNames():
    url_full = url + "/api/v1/label/__name__/values"
    logging.prog('url_full: ' + url_full)
    data = ""
    response = getRequest(url_full, token, data)
    names = response.json()['data']
    logging.debug("names: " + str(names))
    return names
def getIfMetricExists(metric):
    url_full = url + "/api/v1/query"
    logging.prog('url_full: ' + url_full)
    params = { 'query': "absent(absent(" + metric + "))"}		
    response = getRequest(url_full, token, params)
    data = response.json()['data']
    jsonData = json.loads(str(data).replace("'", '"'))
    logging.debug("data: " + str(jsonData))
    if str(jsonData["result"]) == '[]':
        logging.debug("Metric " + metric + " is missing")
        return False
    else:
        logging.debug("Metric " + metric + " exists")
        return True
def getQueryRange(query):
	params = { 'query': query,
				'start': startQueryTime,
				'end': endQueryTime,
				'step': step}					
	url_full = url + "/api/v1/query_range"
	response = getRequest(url_full, token, params)
	logging.debug("Status code: " + str(response.status_code))
	if response.status_code >= 300:
		logging.error("Status code: " + str(response.status_code))
		logging.error("Prometheus query failed")
		logging.error(params)
		logging.error(response)
		logging.error(response.content)
		exit()
	data = response.json()['data']['result']
	return data
def getQuery(url, token, query):
	logging.debug("getQuery")
	params = { 'query': query}		
	url_full = url + "/api/v1/query"
	response = getRequest(url_full, token, params)
	logging.debug("Status code: " + str(response.status_code))
	data = response.json()['data']['result']
	return data

#Definitions
def defineQueryDictionary():
	#CUSTOMIZE -  Add queries here
	
	queryDictionary["nodes"] = {}
	queryDictionary["nodes"]["standard"] =        'REPLACEMETRICNAME'
	queryDictionary["nodes"]["rate"] =            'sum(rate(REPLACEMETRICNAME{}[REPLACERATE])) by (node)'
	
	queryDictionary["disk"] = {}
	queryDictionary["disk"]["standard"] =        'REPLACEMETRICNAME'
	
	queryDictionary["namespace"] = {}
	queryDictionary["namespace"]["standard"] =        'sum(REPLACEMETRICNAME{namespace=~"REPLACENAMESPACE"}) by (namespace)'
	queryDictionary["namespace"]["rate"] =            'sum(rate(REPLACEMETRICNAME{namespace!="",container!~"POD|"}[REPLACERATE])) by (namespace)'
	queryDictionary["namespace"]["podOnlyRate"] =     'sum(rate(REPLACEMETRICNAME{namespace!=""}[REPLACERATE])) by (namespace)'
	queryDictionary["namespace"]["percent"] =         '(sum(increase(REPLACEMETRICNAME{namespace!="",container!~"POD|"}[REPLACERATE])) by (namespace) / sum(increase(REPLACESECONDMETRICNAME{namespace!="",container!~"POD|"}[REPLACERATE])) by (namespace))'
	
	queryDictionary["pod_detail"] = {}
	queryDictionary["pod_detail"]["standard"] =       'sum(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}* on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload,pod)'
	queryDictionary["pod_detail"]["rate"] =           'sum(rate(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])* on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload,pod)'
	queryDictionary["pod_detail"]["percent"] =        '(sum(increase(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (pod) / sum(increase(REPLACESECONDMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (pod)) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}'
	queryDictionary["pod_detail"]["podOnlyRate"] =    'sum(rate(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX"}[REPLACERATE])* on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload,pod)' #Used for network stats which don't have container level details which throws off the container!~"POD|"
	queryDictionary["container_detail"] = {}
	queryDictionary["container_detail"]["standard"] = 'sum(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}* on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload,pod,container)'
	queryDictionary["container_detail"]["rate"] =     'sum(rate(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE]) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload,pod,container)'
	queryDictionary["container_detail"]["percent"] =  '(sum(increase(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (container,pod) / sum(increase(REPLACESECONDMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (container,pod)) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}'
	
	queryDictionary["pod_avg"] = {}
	queryDictionary["pod_avg"]["standard"] =          'avg(avg(sum(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}) by (pod)) by (pod) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{} ) by (namespace, workload_type, workload)'
	queryDictionary["pod_avg"]["rate"] =              'avg(avg(sum(rate(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (pod)) by (pod) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{} ) by (namespace, workload_type, workload)'
	queryDictionary["pod_avg"]["percent"] =           'avg((sum(increase(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (pod) / sum(increase(REPLACESECONDMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (pod)) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload)'
	queryDictionary["pod_avg"]["podOnlyRate"] =       'avg(avg(sum(rate(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX"}[REPLACERATE])) by (pod)) by (pod) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{} ) by (namespace, workload_type, workload)' #Used for network stats which don't have container level details which throws off the container!~"POD|"
	queryDictionary["container_avg"] = {}
	queryDictionary["container_avg"]["standard"] =    'avg(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"} * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload, container)'
	queryDictionary["container_avg"]["rate"] =        'avg(rate(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE]) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload, container)'
	queryDictionary["container_avg"]["percent"] =     'avg(sum(increase(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (container,pod) / sum(increase(REPLACESECONDMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (container,pod)) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload, container)'
	
	queryDictionary["pod_sum"] = {}
	queryDictionary["pod_sum"]["standard"] =          'sum(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"} * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload)'
	queryDictionary["pod_sum"]["rate"] =              'sum(rate(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE]) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload)'
	queryDictionary["pod_sum"]["percent"] =           'sum((sum(increase(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (pod) / sum(increase(REPLACESECONDMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (pod)) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload)'
	queryDictionary["pod_sum"]["podOnlyRate"] =       'sum(rate(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX"}[REPLACERATE]) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload)'
	queryDictionary["container_sum"] = {}
	queryDictionary["container_sum"]["standard"] =    'sum(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"} * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload, container)'
	queryDictionary["container_sum"]["rate"] =        'sum(rate(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE]) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload, container)'
	queryDictionary["container_sum"]["percent"] =     'sum((sum(increase(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (container,pod) / sum(increase(REPLACESECONDMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}[REPLACERATE])) by (container,pod)) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload, container)'

	queryDictionary["count"] = {}
	queryDictionary["count"]["pod"] =         'count(avg(sum(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"}) by (pod)) by (pod) * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{} ) by (namespace, workload_type, workload)'
	queryDictionary["count"]["container"] =   'count(count(REPLACEMETRICNAME{namespace="REPLACENAMESPACE",pod=~"REPLACEPODREGEX",pod!~"REPLACEPODNREGEX",container!~"POD|"} * on(namespace, pod) group_left(workload, workload_type) namespace_workload_pod:kube_pod_owner:relabel{}) by (namespace, workload_type, workload,pod,container)) by (namespace, workload_type, workload, container)'
def defineMetricWorkloadDictionary(groupingType, namespace):
	global metricWorkloadDictionary
	metricWorkloadDictionary = {}
	global metricChacteristicDictionary 
	metricChacteristicDictionary = {}			
	global summaryColumnFreeze
	summaryColumnFreeze = 1
	if ( namespace == "cluster"):
		namespace = ".*"

	#CUSTOMIZE - Add prebuilt queries here:
	if groupingType in groupsForReqLimAll:
		summaryReqLimListUsed = configDictionary["summaryReqLimListNodes"]
	else:
		summaryReqLimListUsed = configDictionary["summaryReqLimList"]
					
	if "nodes" in groupingType: 
		metricWorkloadDictionary["numCPUs"]      = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","instance:node_num_cpu:sum")
		if newPrometheus:
			metricWorkloadDictionary["cpuReq"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(kube_pod_container_resource_requests{container!~'POD|',resource='cpu'}) by (node)")
			metricWorkloadDictionary["cpuLim"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(kube_pod_container_resource_limits{container!~'POD|',resource='cpu'}) by (node)")	
		else:
			metricWorkloadDictionary["cpuReq"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(kube_pod_container_resource_requests_cpu_cores{container!~'POD|'}) by (node)")
			metricWorkloadDictionary["cpuLim"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(kube_pod_container_resource_limits_cpu_cores{container!~'POD|'}) by (node)")		
		metricWorkloadDictionary["CPU"]          = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","instance:node_cpu:rate:sum")		
		metricChacteristicDictionary["numCPUs"]  = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': configDictionary["summaryReqLimListNodes"]}
		metricChacteristicDictionary["cpuReq"]   = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': configDictionary["summaryReqLimListNodes"]}
		metricChacteristicDictionary["cpuLim"]   = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': configDictionary["summaryReqLimListNodes"]}		
		metricChacteristicDictionary["CPU"]      = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': configDictionary["cpuSummaryList"]}
		
		metricWorkloadDictionary["MemUtil"]      = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","instance:node_memory_utilisation:ratio")
		if newPrometheus:
			metricWorkloadDictionary["memReq"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(kube_pod_container_resource_requests{container!~'POD|',resource='memory'}) by (node)")
			metricWorkloadDictionary["memLim"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(kube_pod_container_resource_limits{container!~'POD|',resource='memory'}) by (node)")
		else:
			metricWorkloadDictionary["memReq"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(kube_pod_container_resource_requests_memory_bytes{container!~'POD|'}) by (node)")
			metricWorkloadDictionary["memLim"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(kube_pod_container_resource_limits_memory_bytes{container!~'POD|'}) by (node)")
		metricWorkloadDictionary["MemTot"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","node_memory_MemTotal_bytes")
		metricWorkloadDictionary["memUse"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(node_memory_MemTotal_bytes - node_memory_MemFree_bytes) by (instance)")
		metricWorkloadDictionary["MemFree"]      = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","node_memory_MemFree_bytes")
		metricWorkloadDictionary["MemAct"]       = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","node_memory_Active_bytes")
		metricWorkloadDictionary["BufCache"]     = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","sum(node_memory_Buffers_bytes + node_memory_Cached_bytes) by (instance)")
		metricChacteristicDictionary["MemTot"]   = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		metricChacteristicDictionary["memReq"]   = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["summaryReqLimListNodes"]}
		metricChacteristicDictionary["memLim"]   = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["summaryReqLimListNodes"]}
		metricChacteristicDictionary["MemUtil"]  = {'allSheetName': '', 'dataFormat': percentFormat[groupingType], 'dataFormatSummary': percentFormat["summary"], 'divisor': 1, 'unit': " (%)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		metricChacteristicDictionary["memUse"]   = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		metricChacteristicDictionary["MemFree"]  = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		metricChacteristicDictionary["MemAct"]   = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		metricChacteristicDictionary["BufCache"] = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		
		#metricWorkloadDictionary["TX"]     = queryDictionary["nodes"]["rate"].replace("REPLACEMETRICNAME","container_network_transmit_bytes_total").replace("REPLACERATE",arg.rate)
		#metricWorkloadDictionary["RX"]     = queryDictionary["nodes"]["rate"].replace("REPLACEMETRICNAME","container_network_receive_bytes_total").replace("REPLACERATE",arg.rate)
		#instance:node_network_receive_bytes_excluding_lo:rate1m{job=\"node-exporter\", instance=\"$instance\"}",
		metricWorkloadDictionary["nodeTX"]     = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","instance:node_network_transmit_bytes_excluding_lo:rate1m").replace("REPLACERATE",arg.rate)
		metricWorkloadDictionary["nodeRX"]     = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","instance:node_network_receive_bytes_excluding_lo:rate1m").replace("REPLACERATE",arg.rate)
		metricWorkloadDictionary["podsTX"]      = queryDictionary["nodes"]["rate"].replace("REPLACEMETRICNAME","container_network_transmit_bytes_total").replace("REPLACERATE",arg.rate)
		metricWorkloadDictionary["podsRX"]      = queryDictionary["nodes"]["rate"].replace("REPLACEMETRICNAME","container_network_receive_bytes_total").replace("REPLACERATE",arg.rate)
		metricChacteristicDictionary["nodeTX"] = {'allSheetName': 'All-Net', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1024, 'unit': " (KiB/sec)", 'printUnit': "int", 'summaryList': configDictionary["netSummaryList"]}
		metricChacteristicDictionary["nodeRX"] = {'allSheetName': 'All-Net', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1024, 'unit': " (KiB/sec)", 'printUnit': "int", 'summaryList': configDictionary["netSummaryList"]}
		metricChacteristicDictionary["podsTX"]  = {'allSheetName': 'All-Net', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1024, 'unit': " (KiB/sec)", 'printUnit': "int", 'summaryList': configDictionary["netSummaryList"]}
		metricChacteristicDictionary["podsRX"]  = {'allSheetName': 'All-Net', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1024, 'unit': " (KiB/sec)", 'printUnit': "int", 'summaryList': configDictionary["netSummaryList"]}
	
	elif "disk" in groupingType: 
	# https://www.robustperception.io/mapping-iostat-to-the-node-exporters-node_disk_-metrics
		metricWorkloadDictionary["rps5"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","rate(node_disk_reads_completed_total{device!~'nbd.*'}[5m])") 
		metricWorkloadDictionary["wps5"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","rate(node_disk_writes_completed_total{device!~'nbd.*'}[5m])")
		metricChacteristicDictionary["rps5"] = {'allSheetName': 'All-TPS', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (ops)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}	
		metricChacteristicDictionary["wps5"] = {'allSheetName': 'All-TPS', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (ops)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}	
		
		metricWorkloadDictionary["avgqu_sz1"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","instance_device:node_disk_io_time_weighted_seconds:rate1m{device!~'nbd.*'}")
		metricWorkloadDictionary["avgqu_sz5"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","rate(node_disk_io_time_weighted_seconds_total{device!~'nbd.*'}[5m])")
		metricChacteristicDictionary["avgqu_sz1"] = {'allSheetName': 'All-QSz', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (lenght)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}	
		metricChacteristicDictionary["avgqu_sz5"] = {'allSheetName': 'All-QSz', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (lenght)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}
		
		metricWorkloadDictionary["r_await5"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","rate(node_disk_read_time_seconds_total{device!~'nbd.*'}[5m]) / rate(node_disk_reads_completed_total[5m])") 
		metricWorkloadDictionary["w_await5"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","rate(node_disk_write_time_seconds_total{device!~'nbd.*'}[5m]) / rate(node_disk_writes_completed_total[5m])")
		metricChacteristicDictionary["r_await5"] = {'allSheetName': 'All-AWAIT', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': .001, 'unit': " (ms)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}	
		metricChacteristicDictionary["w_await5"] = {'allSheetName': 'All-AWAIT', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': .001, 'unit': " (ms)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}
		
		metricWorkloadDictionary["util1"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","instance_device:node_disk_io_time_seconds:rate1m{device!~'nbd.*'}")
		metricWorkloadDictionary["util5"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","rate(node_disk_io_time_seconds_total{device!~'nbd.*'}[5m])")	
		metricChacteristicDictionary["util1"] = {'allSheetName': 'All-Util', 'dataFormat': percentFormat[groupingType], 'dataFormatSummary': percentFormat["summary"], 'divisor': 1, 'unit': " (%)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}
		metricChacteristicDictionary["util5"] = {'allSheetName': 'All-Util', 'dataFormat': percentFormat[groupingType], 'dataFormatSummary': percentFormat["summary"], 'divisor': 1, 'unit': " (%)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}
		
		metricWorkloadDictionary["rkBs5"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","rate(node_disk_read_bytes_total{device!~'nbd.*'}[5m])")
		metricWorkloadDictionary["wkBs5"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","rate(node_disk_written_bytes_total{device!~'nbd.*'}[5m])") 
		metricChacteristicDictionary["rkBs5"] = {'allSheetName': 'All-BPS', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1024, 'unit': " (KiB/sec)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}
		metricChacteristicDictionary["wkBs5"] = {'allSheetName': 'All-BPS', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1024, 'unit': " (KiB/sec)", 'printUnit': "int", 'summaryList': configDictionary["diskSummaryList"]}	
		
	elif "filesystem" in groupingType: 		
		metricWorkloadDictionary["fs_total"]     = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","node_filesystem_size_bytes") 
		metricWorkloadDictionary["fs_used"]      = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","node_filesystem_size_bytes - node_filesystem_avail_bytes") 
		metricChacteristicDictionary["fs_total"] = {'allSheetName': 'All-FS', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (MiB)", 'printUnit': "int", 'summaryList': configDictionary["fsSummaryList"]}
		metricChacteristicDictionary["fs_used"]  = {'allSheetName': 'All-FS', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (MiB)", 'printUnit': "int", 'summaryList': configDictionary["fsSummaryList"]}
		
		#metricWorkloadDictionary["fs_util"] = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","1 - (max without (mountpoint, fstype) (node_filesystem_avail_bytes{}) / max without (mountpoint, fstype) (node_filesystem_size_bytes{}))") # .000  decimalFormat
	elif "pv" in groupingType: 			
		metricWorkloadDictionary["pv_used"]      = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","kubelet_volume_stats_used_bytes") #0,000 / 1024 / 1024    integerFormat
		metricWorkloadDictionary["pv_total"]     = queryDictionary["nodes"]["standard"].replace("REPLACEMETRICNAME","kubelet_volume_stats_capacity_bytes") #0,000 / 1024 / 1024  integerFormat
		metricChacteristicDictionary["pv_used"]  = {'allSheetName': 'All-PV', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (MiB)", 'printUnit': "int", 'summaryList': configDictionary["pvSummaryList"]}
		metricChacteristicDictionary["pv_total"] = {'allSheetName': 'All-PV', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (MiB)", 'printUnit': "int", 'summaryList': configDictionary["pvSummaryList"]}
	
	else:
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.cpu or arg.cpur or arg.cpuUser or arg.cpuSys or arg.throttle or arg.reqlim or arg.wss or arg.rss or arg.cache or arg.memUse or arg.network or arg.probes:
			logging.more("defineMetricWorkloadDictionary   At least one metric stat was provided as an argument")
		else:
			logging.prog("defineMetricWorkloadDictionary   No metric stat was provided as an argument")
			arg.keyMetrics = True	
		
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.reqlim:
			summaryColumnFreeze+=2			
			if newPrometheus:
				metricWorkloadDictionary["cpuReq"]       = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","kube_pod_container_resource_requests").replace("REPLACENAMESPACE", namespace + '",resource="cpu')
				metricWorkloadDictionary["cpuLim"]       = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","kube_pod_container_resource_limits").replace("REPLACENAMESPACE", namespace + '",resource="cpu')
			else:
				metricWorkloadDictionary["cpuReq"]       = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","kube_pod_container_resource_requests_cpu_cores").replace("REPLACENAMESPACE", namespace)
				metricWorkloadDictionary["cpuLim"]       = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","kube_pod_container_resource_limits_cpu_cores").replace("REPLACENAMESPACE", namespace)
			metricChacteristicDictionary["cpuReq"]   = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': summaryReqLimListUsed}
			metricChacteristicDictionary["cpuLim"]   = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': summaryReqLimListUsed}
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.reqlim:
			summaryColumnFreeze+=2
			if newPrometheus:
				metricWorkloadDictionary["memReq"]       = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","kube_pod_container_resource_requests").replace("REPLACENAMESPACE", namespace + '",resource="memory')
				metricWorkloadDictionary["memLim"]       = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","kube_pod_container_resource_limits").replace("REPLACENAMESPACE", namespace + '",resource="memory')
			else:
				metricWorkloadDictionary["memReq"]       = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","kube_pod_container_resource_requests_memory_bytes").replace("REPLACENAMESPACE", namespace)
				metricWorkloadDictionary["memLim"]       = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","kube_pod_container_resource_limits_memory_bytes").replace("REPLACENAMESPACE", namespace)
			metricChacteristicDictionary["memReq"]       = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': summaryReqLimListUsed}
			metricChacteristicDictionary["memLim"]       = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': summaryReqLimListUsed}

		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics:
			if "detail" not in groupingType:
				if "pod" in groupingType:
					metricWorkloadDictionary["count"] = queryDictionary["count"]["pod"].replace("REPLACEMETRICNAME","container_memory_rss").replace("REPLACENAMESPACE", namespace)
					metricChacteristicDictionary["count"]   = {'allSheetName': '', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1, 'unit': " (int)", 'printUnit': "int", 'summaryList': configDictionary["countSummaryList"]}
				if "container" in groupingType:
					metricWorkloadDictionary["count"] = queryDictionary["count"]["container"].replace("REPLACEMETRICNAME","container_memory_rss").replace("REPLACENAMESPACE", namespace)
					metricChacteristicDictionary["count"]   = {'allSheetName': '', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1, 'unit': " (int)", 'printUnit': "int", 'summaryList': configDictionary["countSummaryList"]}

		if arg.report                  or arg.allMetrics                   or arg.allCpu or arg.cpu:		
			metricWorkloadDictionary["CPU"]         = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","node_namespace_pod_container:container_cpu_usage_seconds_total:sum_rate").replace("REPLACENAMESPACE", namespace)
			metricChacteristicDictionary["CPU"]     = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': configDictionary["cpuSummaryList"]}
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.allCpu or arg.cpur:	
			metricWorkloadDictionary["CPUr"]        = queryDictionary[groupingType]["rate"].replace("REPLACEMETRICNAME","container_cpu_usage_seconds_total").replace("REPLACENAMESPACE", namespace).replace("REPLACERATE",arg.rate)
			metricChacteristicDictionary["CPUr"]    = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': configDictionary["cpuSummaryList"]}
		if arg.report                  or arg.allMetrics                   or arg.allCpu or arg.cpuUser:
			metricWorkloadDictionary["CPU_Usr"]     = queryDictionary[groupingType]["rate"].replace("REPLACEMETRICNAME","container_cpu_user_seconds_total").replace("REPLACENAMESPACE", namespace).replace("REPLACERATE",arg.rate)
			metricChacteristicDictionary["CPU_Usr"] = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': configDictionary["cpuSummaryList"]}
		if arg.report                  or arg.allMetrics                   or arg.allCpu or arg.cpuSys:
			metricWorkloadDictionary["CPU_Sys"]     = queryDictionary[groupingType]["rate"].replace("REPLACEMETRICNAME","container_cpu_system_seconds_total").replace("REPLACENAMESPACE", namespace).replace("REPLACERATE",arg.rate)
			metricChacteristicDictionary["CPU_Sys"] = {'allSheetName': 'All-CPU', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (cores)", 'printUnit': "dec", 'summaryList': configDictionary["cpuSummaryList"]}
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.allCpu or arg.throttle:
			metricWorkloadDictionary["ThrlSec"]        = queryDictionary[groupingType]["rate"].replace("REPLACEMETRICNAME","container_cpu_cfs_throttled_seconds_total").replace("REPLACENAMESPACE", namespace).replace("REPLACERATE",arg.rate)
			metricWorkloadDictionary["ThrlPct"]        = queryDictionary[groupingType]["percent"].replace("REPLACEMETRICNAME","container_cpu_cfs_throttled_periods_total").replace("REPLACESECONDMETRICNAME","container_cpu_cfs_periods_total").replace("REPLACENAMESPACE", namespace).replace("REPLACERATE",arg.rate)
			metricChacteristicDictionary["ThrlSec"]    = {'allSheetName': '', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1, 'unit': " (sec)", 'printUnit': "dec", 'summaryList': configDictionary["cpuSummaryList"]}
			metricChacteristicDictionary["ThrlPct"]    = {'allSheetName': '', 'dataFormat': percentFormat[groupingType], 'dataFormatSummary': percentFormat["summary"], 'divisor': 1, 'unit': " (%)", 'printUnit': "dec", 'summaryList': configDictionary["cpuSummaryList"]}
		
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.allMem or arg.wss:
			metricWorkloadDictionary["WSS"]        = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","container_memory_working_set_bytes").replace("REPLACENAMESPACE", namespace)
			metricChacteristicDictionary["WSS"]    = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.allMem or arg.rss:
			metricWorkloadDictionary["RSS"]        = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","container_memory_rss").replace("REPLACENAMESPACE", namespace)
			metricChacteristicDictionary["RSS"]    = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.allMem or arg.cache:
			metricWorkloadDictionary["Cache"]      = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","container_memory_cache").replace("REPLACENAMESPACE", namespace)
			metricChacteristicDictionary["Cache"]  = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.allMem or arg.mmap:
			metricWorkloadDictionary["mmap"]     = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","container_memory_mapped_file").replace("REPLACENAMESPACE", namespace)
			metricChacteristicDictionary["mmap"] = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.allMem or arg.memUse:
			metricWorkloadDictionary["memUse"]     = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","container_memory_usage_bytes").replace("REPLACENAMESPACE", namespace)
			metricChacteristicDictionary["memUse"] = {'allSheetName': 'All-Mem', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memSummaryList"]}
		
		if arg.report or arg.keyReport or arg.allMetrics or arg.keyMetrics or arg.network:
			if "container" not in groupingType:
				metricWorkloadDictionary["TX"]     = queryDictionary[groupingType]["podOnlyRate"].replace("REPLACEMETRICNAME","container_network_transmit_bytes_total").replace("REPLACENAMESPACE", namespace).replace("REPLACERATE",arg.rate)
				metricWorkloadDictionary["RX"]     = queryDictionary[groupingType]["podOnlyRate"].replace("REPLACEMETRICNAME","container_network_receive_bytes_total").replace("REPLACENAMESPACE", namespace).replace("REPLACERATE",arg.rate)
				metricChacteristicDictionary["TX"] = {'allSheetName': 'All-Net', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1024, 'unit': " (KiB/sec)", 'printUnit': "int", 'summaryList': configDictionary["netSummaryList"]}
				metricChacteristicDictionary["RX"] = {'allSheetName': 'All-Net', 'dataFormat': decimalFormat[groupingType], 'dataFormatSummary': decimalFormat["summary"], 'divisor': 1024, 'unit': " (KiB/sec)", 'printUnit': "int", 'summaryList': configDictionary["netSummaryList"]}

		if arg.report                  or arg.allMetrics                   or arg.probes:
			metricWorkloadDictionary["Restarts"]     = queryDictionary[groupingType]["standard"].replace("REPLACEMETRICNAME","kube_pod_container_status_restarts_total").replace("REPLACENAMESPACE", namespace)
			metricChacteristicDictionary["Restarts"]     = {'allSheetName': 'Probes', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1, 'unit': " (int)", 'printUnit': "int", 'summaryList': configDictionary["probeSummaryList"]}
			
		
	#Add all of the loaded metrics into the summary 
	metricDataSummaryDictionary[groupingType] = {}
	for metric in metricWorkloadDictionary:
		logging.prog(getCurrentMemoryUsage() + "defineMetricWorkloadDictionary: Adding metric " + metric + " to metricDataSummaryDictionary")
		metricDataSummaryDictionary[groupingType][metric] = {}
		
	#CUSTOMIZE Adding in formula calculations
	metrics = []
	if "memReq" in metricChacteristicDictionary: #If memReq is there, all of the cpu/mem req/lim are there
		logging.debug("defineMetricWorkloadDictionary memReq")
		metricChacteristicDictionary["memReq memLim ratio"]   = {'allSheetName': 'calculated', 'dataFormat': percentFormat[groupingType], 'dataFormatSummary': percentFormat["summary"], 'divisor': 1048576, 'unit': " (%)", 'printUnit': "int", 'summaryList': summaryReqLimListUsed}
		metricChacteristicDictionary["memLim memReq diff"]    = {'allSheetName': 'calculated', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': summaryReqLimListUsed}
		for metric in ["memReq memLim ratio", "memLim memReq diff"]:
			metrics.append(metric)
		
		if "CPUr" in metricChacteristicDictionary:
			logging.debug("defineMetricWorkloadDictionary CPUr")
			metricChacteristicDictionary["CPUr cpuReq ratio"]   = {'allSheetName': 'calculated', 'dataFormat': percentFormat[groupingType], 'dataFormatSummary': percentFormat["summary"], 'divisor': 1, 'unit': " (%)", 'printUnit': "dec", 'summaryList': configDictionary["cpuCalcSummaryList"]}
			for metric in ["CPUr cpuReq ratio"]:
				metrics.append(metric)
				
		if "memUse" in metricChacteristicDictionary:
			logging.debug("defineMetricWorkloadDictionary memUse")
			metricChacteristicDictionary["memUse memLim ratio"]  = {'allSheetName': 'calculated', 'dataFormat': percentFormat[groupingType], 'dataFormatSummary': percentFormat["summary"], 'divisor': 1048576, 'unit': " (%)", 'printUnit': "int", 'summaryList': configDictionary["memCalcSummaryList"]}
			metricChacteristicDictionary["memLim memUse diff"]   = {'allSheetName': 'calculated', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memCalcSummaryList"]}
			for metric in ["memUse memLim ratio", "memLim memUse diff"]:
				metrics.append(metric)
				
		if "RSS" in metricChacteristicDictionary:
			logging.debug("defineMetricWorkloadDictionary RSS")
			metricChacteristicDictionary["RSS memLim ratio"]  = {'allSheetName': 'calculated', 'dataFormat': percentFormat[groupingType], 'dataFormatSummary': percentFormat["summary"], 'divisor': 1048576, 'unit': " (%)", 'printUnit': "int", 'summaryList': configDictionary["memCalcSummaryList"]}
			metricChacteristicDictionary["memLim RSS diff"]   = {'allSheetName': 'calculated', 'dataFormat': integerFormat[groupingType], 'dataFormatSummary': integerFormat["summary"], 'divisor': 1048576, 'unit': " (Mi)", 'printUnit': "int", 'summaryList': configDictionary["memCalcSummaryList"]}
			for metric in ["RSS memLim ratio", "memLim RSS diff"]:
				metrics.append(metric)
		
		for memStat in ["RSS", "WSS", "Cache", "memUse"]:
			if memStat in metricChacteristicDictionary:
				logging.debug("defineMetricWorkloadDictionary " + memStat)
				formula = memStat + " memLim ratio"
				metricChacteristicDictionary[formula]   = {'allSheetName': 'calculated', 'dataFormat': percentFormat[groupingType], 'dataFormatSummary': percentFormat["summary"], 'divisor': 1048576, 'unit': " (%)", 'printUnit': "int", 'summaryList': configDictionary["memCalcSummaryList"]}
				metrics.append(formula)
	
	for metric in metrics:
		logging.prog(getCurrentMemoryUsage() + "defineMetricWorkloadDictionary: Adding calculation metric " + metric + " to metricDataSummaryDictionary")
		metricDataSummaryDictionary[groupingType][metric] = {}
def generateQuery(item, regex, nregex, index, groupingType):
	query = item.replace("REPLACEPODREGEX",regex).replace("REPLACEPODNREGEX",nregex)
	if index > 0: #Building special query for the pods that need merging together
		if "sum" in groupingType:
			query = "sum(" + query + ")"
		if "avg" in groupingType:
			query = "avg(" + query + ")"
		if "container" in groupingType:
			query = query + " by (container)"
	return query
def generateGrouping(namespace):
	#CUSTOMIZE - Add groupings
	groupingDictionary = {}
	if namespace == "cluster" :
		if arg.report or arg.keyReport or arg.cluster or arg.namespaceTotals:
			groupingDictionary["namespace"] = {}
			
		if arg.report or arg.keyReport or arg.cluster or arg.nodes:
			groupingDictionary["nodes"] = {}
			
		if arg.report or arg.keyReport or arg.cluster or arg.disk:
			groupingDictionary["disk"] = {}
			
		if arg.report or arg.keyReport or arg.cluster or arg.filesystem:
			groupingDictionary["filesystem"] = {}
			
		if arg.report or arg.keyReport or arg.cluster or arg.pv:
			groupingDictionary["pv"] = {}
	else:
		if arg.sum or arg.report or arg.keyReport:
			if arg.container or arg.report or arg.keyReport: 
				groupingDictionary["container_sum"] = {}
			if arg.pod or arg.report or arg.keyReport: 
				groupingDictionary["pod_sum"] = {}
				
		if arg.avg or arg.report:	
			if arg.container or arg.report or arg.keyReport: 
				groupingDictionary["container_avg"] = {}
			if arg.pod or arg.report: 
				groupingDictionary["pod_avg"] = {}
				
		if not arg.noDetail and (arg.container or arg.report or arg.keyReport):
			groupingDictionary["container_detail"] = {}	
		if not arg.noDetail and (not groupingDictionary or arg.pod or arg.report or arg.keyReport):
			groupingDictionary["pod_detail"] = {}
		
	return groupingDictionary
def generateMetricDataDictionaryKey(groupingType, metricType):
	key = groupingType + "-" + metricType
	return key
def generateStartswithString(groupingType):
	startswithString = groupingType + "-"
	return startswithString
def generatePodContainerList(groupingType):
	logging.prog(getCurrentMemoryUsage() + "generatePodContainerList  metricDataDictionary groupingType: " + groupingType)
	setOfPodsAndContainers = set()
	
	key_list = generateListOfKeys(metricDataDictionary, groupingType + "-")
	for key in key_list:
		for name in metricDataDictionary[key]:
			logging.debug("generatePodContainerList  Adding: " + name)
			setOfPodsAndContainers.add(name)
	if logging.MORE >= logging.root.level:
		for name in sorted(setOfPodsAndContainers):
			logging.more("generatePodContainerList  groupingType:" + groupingType + "  name: " + name)
	return setOfPodsAndContainers
def generateTimestamps(groupingType, worksheetName):
	logging.prog(getCurrentMemoryUsage() + "generateTimestamps worksheets[" + groupingType + "][" + worksheetName +"]")
	worksheetsCounter[groupingType][worksheetName] = 1
	worksheets[groupingType][worksheetName].write(0, 0, "Timestamp", textWrap[groupingType]["standard"])
	worksheets[groupingType][worksheetName].set_column('A:A', 19)
	worksheets[groupingType][worksheetName].freeze_panes(1, 1)
	index = 1
	for epoch in range(start_epoch, end_epoch+step_int, step_int):
		timestamp = str(time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(epoch)))
		worksheets[groupingType][worksheetName].write(index, 0, timestamp)
		index += 1
def generateSheetNames(groupingType):
	for key in metricDataDictionary:
		groupingType = (key.split('-')[0]).strip()
		metricType = (key.split('-')[1]).strip()
		logging.debug("generateSheetNames groupingType: " + groupingType + "  metricType: " + metricType + "  key: " + key)
		allSheetName = metricChacteristicDictionary[metricType]["allSheetName"]
		#subGenerateSheetNames(allSheetName, groupingType)
		#logging.more("subGenerateSheetNames  allSheetName: " + allSheetName)
		if allSheetName not in worksheets[groupingType] and allSheetName != "":
			logging.more("generateSheetNames ALL worksheets[" + groupingType + "][" + allSheetName +"]")
			worksheets[groupingType][allSheetName] = workbook[groupingType].add_worksheet(allSheetName)
	for key in metricDataDictionary:
		groupingType = (key.split('-')[0]).strip()
		metricType = (key.split('-')[1]).strip()
		sheetName = metricType
		#if "Req" in metricType or "Lim" in metricType:
		if metricType in namesForReqLim:
			sheetName = ""
		else:
			if sheetName not in worksheets[groupingType]:
				logging.more("generateSheetNames worksheets[" + groupingType + "][" + sheetName +"]")
				worksheets[groupingType][sheetName] = workbook[groupingType].add_worksheet(sheetName)
	for worksheetName in worksheets[groupingType]:
		generateTimestamps(groupingType, worksheetName)
def generateListOfKeys(dictionary, startswithString):
	keyList = []
	for key in dictionary:
		if key.startswith(startswithString):
			keyList.append(key)
	return keyList

#Summary Creation
def evaluateThreshold(metricType, summaryName, function, value, thresholdMessage, unit, message, divisor):
	key = "standard"
	if summaryName in configDictionary[metricType]:
		logging.debug("evaluateThreshold  Found " + summaryName + " in thresholds")	
		key = summaryName
	logging.more("evaluateThreshold  " + metricType + "  Comparing " + str(configDictionary[metricType][key]) + " to " + str(value) + " in " + summaryName + " using key " + key)
	if value > 0 :
		tempArray = configDictionary[metricType][key].split(':')
		lowerBound = tempArray[0]
		upperBound = tempArray[1]
		if lowerBound != "":
			logging.debug("Has lower " + str(lowerBound))
			if value < int(lowerBound):
				if thresholdMessage == "":
					thresholdMessage = configDictionary[metricType]["messageLower"] + " -  " + str(lowerBound) + unit + " vs " 
				thresholdMessage = thresholdMessage + str(int(value)) + " (" + function + ") " + message + ",  "
		if upperBound != "":
			logging.debug("Has upper " + str(upperBound))
			if value > int(upperBound):
				if thresholdMessage == "":
					thresholdMessage = configDictionary[metricType]["messageUpper"] + " -  " + str(upperBound) + unit + " vs " 
				thresholdMessage = thresholdMessage + str(int(value)) + " (" + function + ") " + message + ",  "
	return thresholdMessage
def summaryCalc(groupingType, metricType, summaryName, worksheet, row, column, item1, item2, function, index, arrayLength, printUnit, divisor):
	message = ""
	try:
		item1Value = metricDataSummaryDictionary[groupingType][item1][summaryName][function]
		item2Value = metricDataSummaryDictionary[groupingType][item2][summaryName][function] 
		logging.more("summaryCalc  groupingType " + groupingType + " metricType " + metricType + " function " + function + " item1Value " + str(item1Value) + " item2Value " + str(item2Value) + " divisor " + str(divisor) + " printUnit " + printUnit )
		operation = ""
		if metricType.endswith("ratio"):
			if item2Value != 0:
				resultPrint =  item1Value / item2Value
				result = resultPrint * 100
			else:
				result = 0
				resultPrint = 0
			operation = "/"
		elif metricType.endswith("diff"):
			result =  (item1Value - item2Value) / divisor
			resultPrint = result
			operation = "-"
			
		if printUnit == "dec":
			message = "{:>.2f}{:s}{:<.2f}".format(item1Value/divisor, operation, item2Value/divisor)
		elif printUnit == "per":
			message = "{:>.2f}{:s}{:<.2f}".format(item1Value*100/divisor, operation, item2Value*100/divisor)
		elif printUnit == "int":
			message = "{:>.0f}{:s}{:<.0f}".format(item1Value/divisor, operation, item2Value/divisor)
		else:
			logging.warning("thresholdMessage Could not find printUnit")
	except KeyError:
		result = 0
		resultPrint = 0 
	if index + 1 == arrayLength:
		dataFormat = metricChacteristicDictionary[metricType]["dataFormatSummary"]["right1_boarder"]["black"]
	else:
		dataFormat = metricChacteristicDictionary[metricType]["dataFormatSummary"]["standard"]["black"]
	if worksheet:
		worksheet.write(row, column, str(resultPrint), dataFormat)
		column+=1
	return column, result, message, item1Value, item2Value
def summaryCalculations(groupingType, metricType, summaryName, worksheet, row, column):
	aggArray = metricChacteristicDictionary[metricType]["summaryList"]
	unit = metricChacteristicDictionary[metricType]["unit"]
	printUnit = metricChacteristicDictionary[metricType]["printUnit"]
	divisor = metricChacteristicDictionary[metricType]["divisor"]
	thresholdMessage = ""
	metricTypeArray = metricType.split(' ')
	item1 = metricTypeArray[0]
	item2 = metricTypeArray[1]
	for index,function in enumerate(aggArray):	
		column, value, message, item1Value, item2Value  = summaryCalc(groupingType, metricType, summaryName, worksheet, row, column, item1, item2, function, index, len(aggArray), printUnit, divisor)
		if metricType in configDictionary:		
			if item1Value == 0 or item2Value == 0 :
				logging.debug("metricType " + metricType + " has a zero value, skipping...  ")
			else:
				thresholdMessage = evaluateThreshold(metricType, summaryName, function, value, thresholdMessage, unit, message, divisor)				
		else:
			logging.debug("metricType " + metricType + " is not in configDictionary")
	
	printAnalysisMessage(groupingType, metricType, summaryName, thresholdMessage)
	return column
def summaryWriter(worksheet, row, column, data, metricType, targetColumn, color):
	logging.debug("summaryWriter metricType: " + metricType + " row: " + str(row) + " column: " + str(column) + " targetColumn: " + str(targetColumn) + "  data: " + str(data))
	if metricType: 
	
		color = "black"
		if float(data) == 0.0 :
			color = "black"
		if column == targetColumn:
			format = metricChacteristicDictionary[metricType]["dataFormatSummary"]["right1_boarder"][color]
		else:
			format = metricChacteristicDictionary[metricType]["dataFormatSummary"]["standard"][color]
	else:
		if column == targetColumn:
			format = integerFormat["summary"]["right1_boarder"]["black"]
		else:
			format = integerFormat["summary"]["standard"]["black"]
		
		
	try:
		worksheet.write(row, column, data, format)
	except:
		worksheet.write(row, column, 0, format)
	column+=1
	return column
def iterateSummaryScreen(groupingType, metricType, summaryName, worksheet, row):
	column = 1
	for metricType in metricDataSummaryDictionary[groupingType]:
		logging.debug("iterateSummaryScreen: " + groupingType + " " + metricType + " " + summaryName)
		allSheetName = metricChacteristicDictionary[metricType]["allSheetName"]
		divisor = metricChacteristicDictionary[metricType]["divisor"]
		unit = metricChacteristicDictionary[metricType]["unit"]
		printUnit = metricChacteristicDictionary[metricType]["printUnit"]
		summaryList = metricChacteristicDictionary[metricType]["summaryList"]
		targetColumn = column + len(summaryList) - 1
		
		if "calculated" == allSheetName:
			logging.more("iterateSummaryScreen calculating " + groupingType + " " + metricType + " " + summaryName)
			column = summaryCalculations(groupingType, metricType, summaryName, worksheet, row, column)
		else:
			if summaryName in metricDataSummaryDictionary[groupingType][metricType]:					
				name = summaryName + unit
				datapointCount = metricDataSummaryDictionary[groupingType][metricType][summaryName]["datapointCount"]
				count = metricDataSummaryDictionary[groupingType][metricType][summaryName]["count"]
				total = metricDataSummaryDictionary[groupingType][metricType][summaryName]["total"] 
				minimum = metricDataSummaryDictionary[groupingType][metricType][summaryName]["min"] / divisor
				maximum = metricDataSummaryDictionary[groupingType][metricType][summaryName]["max"] / divisor
				start = metricDataSummaryDictionary[groupingType][metricType][summaryName]["start"] / divisor
				end = metricDataSummaryDictionary[groupingType][metricType][summaryName]["end"] / divisor
				change = end - start
				
				#Re
				metricDataSummaryDictionary[groupingType][metricType][summaryName]["change"] = change
				metricDataSummaryDictionary[groupingType][metricType][summaryName]["p25"] = metricDataSummaryDictionary[groupingType][metricType][summaryName]["p25T"] / count 
				metricDataSummaryDictionary[groupingType][metricType][summaryName]["p50"] = metricDataSummaryDictionary[groupingType][metricType][summaryName]["p50T"] / count
				metricDataSummaryDictionary[groupingType][metricType][summaryName]["p75"] = metricDataSummaryDictionary[groupingType][metricType][summaryName]["p75T"] / count
				p25 = metricDataSummaryDictionary[groupingType][metricType][summaryName]["p25"] / divisor
				p50 = metricDataSummaryDictionary[groupingType][metricType][summaryName]["p50"] / divisor
				p75 = metricDataSummaryDictionary[groupingType][metricType][summaryName]["p75"] / divisor
				
				if datapointCount > 0: 
					metricDataSummaryDictionary[groupingType][metricType][summaryName]["avg"] = total / datapointCount
					average = metricDataSummaryDictionary[groupingType][metricType][summaryName]["avg"] / divisor
				else:
					metricDataSummaryDictionary[groupingType][metricType][summaryName]["avg"] = 0
					average = 0				
				
				#CUSTOMIZE Add summary stuff here 
				if worksheet:
					if column == 1:
						if "detail" in groupingType:
							#column = summaryWriter(worksheet, row, column, str(count), "", column)
							column = summaryWriter(worksheet, row, column, count, "", column, "red")
							targetColumn+=1
					if "min" in summaryList:
						column = summaryWriter(worksheet, row, column, minimum, metricType, targetColumn, "red")
					if "max" in summaryList:
						column = summaryWriter(worksheet, row, column, maximum, metricType, targetColumn, "red")
					if "avg" in summaryList:
						column = summaryWriter(worksheet, row, column, average, metricType, targetColumn, "red")
					if "p25" in summaryList:
						column = summaryWriter(worksheet, row, column, p25, metricType, targetColumn, "red")
					if "p50" in summaryList:
						column = summaryWriter(worksheet, row, column, p50, metricType, targetColumn, "red")
					if "p75" in summaryList:
						column = summaryWriter(worksheet, row, column, p75, metricType, targetColumn, "red")
					if "start" in summaryList:
						column = summaryWriter(worksheet, row, column, start, metricType, targetColumn, "red")
					if "end" in summaryList:
						column = summaryWriter(worksheet, row, column, end, metricType, targetColumn, "red")
					if "change" in summaryList:
						column = summaryWriter(worksheet, row, column, change, metricType, targetColumn, "red")
			
				multiplier=1
				if printUnit == "per":
					multiplier=100
				if printUnit == "int":
					message = "{:<20s} count: {:>2.0f}   dp: {:>6.0f}  s/e: {:>7.0f} {:>7.0f}  chg {:>7.0f}   min: {:>7.0f}   max: {:>7.0f}   avg: {:>7.0f}   pct: {:>7.0f} {:>7.0f} {:>7.0f}".format(metricType + unit, count, datapointCount, start, end, change, minimum, maximum, average, p25, p50, p75)
				else:
					message = "{:<20s} count: {:>2.0f}   dp: {:>6.0f}  s/e: {:>7.2f} {:>7.2f}  chg {:>7.2f}   min: {:>7.2f}   max: {:>7.2f}   avg: {:>7.2f}   pct: {:>7.2f} {:>7.2f} {:>7.2f}".format(metricType + unit, count, datapointCount, start*multiplier, end*multiplier, change*multiplier, minimum*multiplier, maximum*multiplier, average*multiplier, p25*multiplier, p50*multiplier, p75*multiplier)
				
				printSummaryMessage(message)	
			else:
				logging.info("iterateSummaryScreen SKIP " + metricType + " " + summaryName)
def printSummaryHeadersXLSX(groupingType):
	#CUSTOMIZE Add summary stuff here
	worksheet = addSheetName("summary", groupingType)
	
	column=0
	worksheet.write(0, column, "Item", textWrap["summary"]["right2_bottom2_boarder"])
	column+=1
	global summaryColumnFreeze
	if "detail" in groupingType:
		worksheet.write(0, column, "Instances in Summary", textWrap["summary"]["right1_bottom2_boarder"])
		summaryColumnFreeze+=1
		column+=1
	worksheet.freeze_panes(1, summaryColumnFreeze)
	worksheet.set_column('A:A', 50)
	for metricType in metricDataSummaryDictionary[groupingType]:
		unit = metricChacteristicDictionary[metricType]["unit"]
		logging.debug("printSummaryHeadersXLSX metricType: " + metricType)
		aggArray = metricChacteristicDictionary[metricType]["summaryList"]
		#for agg in aggArray:
		#TODO - figure out where extra space is coming in between agg and unit
		for index,agg in enumerate(aggArray):
			header = metricType + "\n" + agg + "\n" + unit
			logging.debug("printSummaryHeadersXLSX Header " + str(column) + " " + header)
			if index + 1 == len(aggArray):
				worksheet.write(0, column, header, textWrap["summary"]["right1_bottom2_boarder"])
			else:
				worksheet.write(0, column, header, textWrap["summary"]["bottom2_boarder"])
			column+=1
	return worksheet
def printSummary(groupingType):
	summaryNameSet = set()
	for metricType in metricDataSummaryDictionary[groupingType]: #Build list of summary names (containers etc)
		for summaryName in metricDataSummaryDictionary[groupingType][metricType]:
			summaryNameSet.add(summaryName)
	if logging.DEBUG >= logging.root.level:
		for summaryName in sorted(summaryNameSet):
			logging.debug("summaryNameSet " + summaryName)
	
	worksheet = printSummaryHeadersXLSX(groupingType)
	row=0
	for summaryName in sorted(summaryNameSet):
		row+=1
		logging.more(getCurrentMemoryUsage() + "printSummary  groupingType: " + groupingType + " summaryName: " + summaryName)
		worksheet.write(row, 0, summaryName, itemTitle["summary"]["right2_boarder"])
		printSummaryMessage("\n---  " + groupingType + "  :  " + summaryName + "  ---")
		iterateSummaryScreen(groupingType, metricType, summaryName, worksheet, row)
def processSummary(groupingType, dataArray, name, title, metricType):
	if groupingType in namesForSummary:
		logging.more("processSummary title: " + title)
		logging.debug("processSummary dataArray: " + str(dataArray))
		temp = [float(x[1]) for x in dataArray]
		logging.verbose("temp: " + title + " " + str(temp))
		total = 0 
		minimum = 0
		maximum = 0 
		datapointCount = 0 
		average = 0 
		start = 0
		end = 0
		p25T = 0
		p50T = 0
		p75T = 0 
		datapointCount = len(dataArray)
		if datapointCount > 0: 
			start = float(dataArray[0][1])
			end = float(dataArray[datapointCount-1][1])
			#logging.info("start: " + str(start) + " end: " + str(end))
			total = sum(temp)
			average = total / datapointCount
			
			sortedArray = sorted(temp)
			#minimum = min(temp) #Already sorted, more efficient to use sortedArray?
			#maximum = max(temp) #Already sorted, more efficient to use sortedArray?
			minimum = sortedArray[0]
			maximum = sortedArray[int(datapointCount-1)]
			p25T = sortedArray[int(datapointCount*0.25)]
			p50T = sortedArray[int(datapointCount*0.5)]
			p75T = sortedArray[int(datapointCount*0.75)]
			
		nameArray = name.split(' ')
		summaryName = (nameArray[0]).strip()
		if "container" in groupingType:
			summaryName = summaryName + " " + (nameArray[2]).strip()
		logging.more("summaryName: " + summaryName + " metricType: " + metricType + "  total: " + str(total) + "  datapointCount: " + str(datapointCount) + "  min: " + str(minimum) + "  max: " + str(maximum) + "  avg: " + str(average) + "  pct: " + str(p25T) + " " + str(p50T) + " " + str(p75T))
		if not summaryName in metricDataSummaryDictionary[groupingType][metricType]:
			metricDataSummaryDictionary[groupingType][metricType][summaryName] = {}
					
		if "min" in metricDataSummaryDictionary[groupingType][metricType][summaryName]:
			if minimum < metricDataSummaryDictionary[groupingType][metricType][summaryName]["min"]:
				metricDataSummaryDictionary[groupingType][metricType][summaryName]["min"] = minimum
		else:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["min"] = minimum
		if "max" in metricDataSummaryDictionary[groupingType][metricType][summaryName]:
			if maximum > metricDataSummaryDictionary[groupingType][metricType][summaryName]["max"]:
				metricDataSummaryDictionary[groupingType][metricType][summaryName]["max"] = maximum
		else:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["max"] = maximum
		
		if "total" in metricDataSummaryDictionary[groupingType][metricType][summaryName]:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["total"] = metricDataSummaryDictionary[groupingType][metricType][summaryName]["total"] + total
		else:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["total"] = total
			
		if "count" in metricDataSummaryDictionary[groupingType][metricType][summaryName]:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["count"] = metricDataSummaryDictionary[groupingType][metricType][summaryName]["count"] + 1
		else:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["count"] = 1
			
		if "datapointCount" in metricDataSummaryDictionary[groupingType][metricType][summaryName]:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["datapointCount"] = metricDataSummaryDictionary[groupingType][metricType][summaryName]["datapointCount"] + datapointCount
		else:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["datapointCount"] = datapointCount
			
		if "start" not in metricDataSummaryDictionary[groupingType][metricType][summaryName]:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["start"] = start
		metricDataSummaryDictionary[groupingType][metricType][summaryName]["end"] = end
			
		if "p25T" in metricDataSummaryDictionary[groupingType][metricType][summaryName]:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["p25T"] = metricDataSummaryDictionary[groupingType][metricType][summaryName]["p25T"] + p25T
		else:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["p25T"] = p25T
		if "p50T" in metricDataSummaryDictionary[groupingType][metricType][summaryName]:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["p50T"] = metricDataSummaryDictionary[groupingType][metricType][summaryName]["p50T"] + p50T
		else:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["p50T"] = p50T
		if "p75T" in metricDataSummaryDictionary[groupingType][metricType][summaryName]:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["p75T"] = metricDataSummaryDictionary[groupingType][metricType][summaryName]["p75T"] + p75T
		else:
			metricDataSummaryDictionary[groupingType][metricType][summaryName]["p75T"] = p75T

#Data Processing
def iteratePrintDataArray(dataArray, printTrue, title, name, groupingType, metricType, sheetName, allSheetName, dataFormat, divisor):
	processSummary(groupingType, dataArray, name, title, metricType)	
	if logging.VERBOSE >= logging.root.level:
		for data in dataArray:
			logging.verbose("time: " + str(data[0]) + " value: " + str(data[1]))
	index = 0
	sheet_index = 0
	if printTrue:
		if sheetName:
			worksheets[groupingType][sheetName].write(sheet_index, worksheetsCounter[groupingType][sheetName], title, textWrap[groupingType]["standard"])
		if allSheetName:
			worksheets[groupingType][allSheetName].write(sheet_index, worksheetsCounter[groupingType][allSheetName], title, textWrap[groupingType]["standard"])
	for epoch in range(start_epoch, end_epoch+step_int, step_int):
		sheet_index += 1
		timestamp = str(time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(epoch)))
		logging.verbose("length: " + str(len(dataArray)) + " " + str(index))
		if len(dataArray) > index:
			logging.verbose("compare: " + str(dataArray[index][0]) + " " + str(epoch))
			if int(dataArray[index][0]) == epoch: 
				logging.verbose("iteratePrintDataArray: " + timestamp + "," + str(dataArray[index][1]))
				if printTrue:
					if sheetName:
						worksheets[groupingType][sheetName].write(sheet_index,worksheetsCounter[groupingType][sheetName],str(float(dataArray[index][1])/divisor),dataFormat)
					if allSheetName:
						worksheets[groupingType][allSheetName].write(sheet_index,worksheetsCounter[groupingType][allSheetName],str(float(dataArray[index][1])/divisor),dataFormat)
				index+= 1
			else:
				logging.debug("iteratePrintDataArray: " + timestamp + "," )
				if printTrue:
					if sheetName:
						worksheets[groupingType][sheetName].write(sheet_index,worksheetsCounter[groupingType][sheetName],"")
					if allSheetName:
						worksheets[groupingType][allSheetName].write(sheet_index,worksheetsCounter[groupingType][allSheetName],"")
		else:
			logging.debug("iteratePrintDataArray: " + timestamp + "," )	
			if printTrue:
				if sheetName:
					worksheets[groupingType][sheetName].write(sheet_index,worksheetsCounter[groupingType][sheetName],"")
				if allSheetName:
					worksheets[groupingType][allSheetName].write(sheet_index,worksheetsCounter[groupingType][allSheetName],"")
def printHashColumn(key, name, metricType, groupingType):
	sheetName = metricType
	if "Req" in metricType or "Lim" in metricType:
		sheetName = ""
		logging.debug("printHashColumn skipping adding " + metricType + " to its own sheet")
	allSheetName = metricChacteristicDictionary[metricType]["allSheetName"]
	dataFormat = metricChacteristicDictionary[metricType]["dataFormat"]["standard"]["black"]
	divisor = metricChacteristicDictionary[metricType]["divisor"]
	unit = metricChacteristicDictionary[metricType]["unit"]

	message = "printHashColumn Printing data for: {:<75s} groupingType: {:<15s} metricType: {:<7s} groupingType: {:<15s} sheetName: {:<7s} allSheetName: {:<7s}".format(name, groupingType, metricType, groupingType, sheetName, allSheetName)
	logging.more(message)
	title = name + " " + metricType + unit
	if name in metricDataDictionary[key]:
		logging.verbose(metricDataDictionary[key][name])
		iteratePrintDataArray(metricDataDictionary[key][name], "true", title, name, groupingType, metricType, sheetName, allSheetName, dataFormat, divisor)
	else:
		logging.debug("Missing " + name + " from " + key + ".  Could be an init or startup container that never used resources.")
		empty = {}
		iteratePrintDataArray(empty, "true", title, name, groupingType, metricType, sheetName, allSheetName, dataFormat, divisor)
	if sheetName:
		worksheetsCounter[groupingType][sheetName] += 1
	if allSheetName:
		worksheetsCounter[groupingType][allSheetName] += 1
def iterateOverKeyList(groupingType, name, keyList):
	logging.more("----------------------------------------------------------------------------------------------------------------------------------------------------------------")
	logging.prog(getCurrentMemoryUsage() + "iterateOverKeyList  groupingType: " + groupingType + "   name: " + name)
	for key in keyList:
		logging.more("iterateOverKeyList key: " + key)	
		groupingTypeRead = (key.split('-')[0]).strip()
		if groupingTypeRead != groupingType:
			logging.error("groupingType: " + groupingType + " does not equal groupingTypeRead: " + groupingTypeRead)
			exit()
		metricType = (key.split('-')[1]).strip()
		printHashColumn(key, name, metricType, groupingType)
def iterateOverSetOfPodsAndContainers(groupingType, startswithString, setOfPodsAndContainers):
	logging.prog(getCurrentMemoryUsage() + "iterateOverSetOfPodsAndContainers  groupingType: " + groupingType)
	keyList = generateListOfKeys(metricDataDictionary, startswithString)
	for name in sorted(setOfPodsAndContainers):
		logging.more("iterateOverSetOfPodsAndContainers startswithString: " + startswithString + "  name: " + name)
		iterateOverKeyList(groupingType, name, keyList)
def postQueryProcessing(groupingType):
	logging.prog(getCurrentMemoryUsage() + "postQueryProcessing  groupingType: " + groupingType )
	setOfPodsAndContainers = generatePodContainerList(groupingType)
	startswithString = generateStartswithString(groupingType)
	generateSheetNames(groupingType)
	
	#Just a debug print
	if logging.VERBOSE >= logging.root.level:
		testIterateMetricDataDictionary()
	
	iterateOverSetOfPodsAndContainers(groupingType, startswithString, setOfPodsAndContainers)
	
	logging.prog(getCurrentMemoryUsage() + "Finished iterateOverSetOfPodsAndContainers, writing to xlsx...")
	logging.info(getCurrentMemoryUsage() + "Writing and closing groupingType: " + groupingType)		
	workbook[groupingType].close()
	clearData(groupingType, startswithString)
def runQueryAndProcess(inDictionary, query, metricType, groupingType, workloadMergeList, regex, index):
	dataset = getQueryRange(query)
	tempDictionary = inDictionary
	for data in dataset:
		jsonData = json.loads(str(data).replace("'", '"'))
		logging.debug("dump: " + json.dumps(str(data)))
		
		name = "empty"
		#CUSTOMIZE
		if ("pv" in groupingType):
			node = ""
			persistentvolumeclaim=""
			if 'node' in jsonData["metric"]:
				node = jsonData["metric"]["node"]
			if 'persistentvolumeclaim' in jsonData["metric"]:
				persistentvolumeclaim = jsonData["metric"]["persistentvolumeclaim"]
				
			if persistentvolumeclaim: #PV space, not using node because it can move?
				name = persistentvolumeclaim
			#if node and persistentvolumeclaim: #PV space
			#	name = node + " " + persistentvolumeclaim
			#else:
			#	logging.info("EMPRY")
			#	exit()
				
			message = "processing  metricType: {:<15s}  groupingType: {:<15s}  name: {:<100s} ".format(metricType, groupingType, name)
			logging.more(message)
		elif ("filesystem" in groupingType):
			device = ""
			node = ""
			instance = ""
			mountpoint = ""
			fstype = ""
			if 'node' in jsonData["metric"]:
				node = jsonData["metric"]["node"]
			if 'instance' in jsonData["metric"]:
				instance = jsonData["metric"]["instance"]
			if 'device' in jsonData["metric"]:
				device = jsonData["metric"]["device"]
			if 'mountpoint' in jsonData["metric"]:
				mountpoint = jsonData["metric"]["mountpoint"]
			if 'fstype' in jsonData["metric"]:
				fstype = jsonData["metric"]["fstype"]
				
			if node and device and mountpoint and fstype:  #Node Filesystem Stats
				name = node + " " + device + " " + mountpoint + " " + fstype
			elif instance and device and mountpoint and fstype:  #Node Filesystem Stats NFS
				name = instance + " " + device + " " + mountpoint + " " + fstype
			elif device and instance: #fs_util
				name = instance + " " + device
			#else:
			#	logging.info("EMPRY")
			#	exit()
				
			message = "processing  metricType: {:<15s}  groupingType: {:<15s}  name: {:<100s} ".format(metricType, groupingType, name)
			logging.more(message)
		elif ("disk" in groupingType):
			device = ""
			instance = ""
			if 'instance' in jsonData["metric"]:
				instance = jsonData["metric"]["instance"]
			if 'device' in jsonData["metric"]:
				device = jsonData["metric"]["device"]
				
			if instance and device: 
				name = instance + " " + device
			elif instance:
				name = instance
				
			message = "processing  metricType: {:<15s}  groupingType: {:<15s}  name: {:<100s} ".format(metricType, groupingType, name)
			logging.more(message)
		elif ("nodes" in groupingType):
			instance = ""
			node = ""
			if 'node' in jsonData["metric"]:
				node = jsonData["metric"]["node"]
			if 'instance' in jsonData["metric"]:
				instance = jsonData["metric"]["instance"]
				
			if node:
				name = node
			elif instance:
				name = instance	
				
			message = "processing  metricType: {:<15s}  groupingType: {:<15s}  name: {:<100s} ".format(metricType, groupingType, name)
			logging.more(message)
		else:
			pod = ""
			container = ""
			workload = ""
			device = ""
			workload_type = ""
			namespace = ""
			if 'workload' in jsonData["metric"]:
				workload = jsonData["metric"]["workload"]
			if 'pod' in jsonData["metric"]:
				pod = jsonData["metric"]["pod"]
			if 'container' in jsonData["metric"]:
				container = jsonData["metric"]["container"]
			if 'workload_type' in jsonData["metric"]:
				workload_type = jsonData["metric"]["workload_type"]
			if 'namespace' in jsonData["metric"]:
				namespace = jsonData["metric"]["namespace"]
		
			if workload and pod and container: #container details
				name = workload + " [" + pod + "] (" + container + ")"
			elif workload and container: #container sum/avg
				name = workload + " [all-pods] (" + container + ")"
			elif workload and pod: #pod details
				name = workload + " [" + pod + "]"
			elif pod and container: #Not used, but just incase
				name = "[" + pod + "] (" + container + ")"
			elif namespace and workload:
				name = workload 
			elif workload: #pod sum/avg
				name = workload 
			elif namespace:
				name = namespace
			elif pod: #Not used, but just incase
				name = "[" + pod + "]"
			elif container: #Not used, but just incase
				if index > 0:
					name = regex + " [all-pods] (" + container + ")"
				else:
					name = "(" + container + ")"
			else: 
				if index > 0:
					name = regex
				else:
					name = "total"	
			message = "processing  metricType: {:<15s}  groupingType: {:<15s}  name: {:<100s} ".format(metricType, groupingType, name)
			logging.more(message)		
			message = "processing  pod: {:<35s} workload: {:<35s} container: {:<35s} workload_type: {:<35s}".format(pod, workload, container, workload_type)
			logging.debug(message)
		
		values = list(jsonData["values"])
		tempDictionary[name] = values
		
		#Just a debug print
		if logging.VERBOSE >= logging.root.level:
			for value in values:
				logging.verbose("time: " + str(time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(value[0]))) + " epoch: " + str(value[0]) + " value: " + str(value[1]))
			testIterateTimesProcessing(values)
		inDictionary = tempDictionary[name]
def runWorkload(groupingType, podregexlist, podnregexlist, namespace, workloadMergeList):
	for index in range(len(podregexlist)):
		for metricType in metricWorkloadDictionary:
			query = generateQuery(metricWorkloadDictionary[metricType], podregexlist[index], podnregexlist[index], index, groupingType)
			key = generateMetricDataDictionaryKey(groupingType, metricType)
			if key not in metricDataDictionary: 
				metricDataDictionary[key] = {}	
			logging.prog(getCurrentMemoryUsage() + "runWorkload  namespace: " + namespace + "  groupingType: " + groupingType + "  metricType: " + metricType + "  podregex: " + podregexlist[index] + "  podnregex: " + podnregexlist[index] + "  index: " + str(index) + "  key: " + key + "\n" + query + "\n---------")		
			runQueryAndProcess(metricDataDictionary[key], query, metricType, groupingType, workloadMergeList, podregexlist[index], index)
	postQueryProcessing(groupingType)

def main():
	init()
	newPrometheus=getIfMetricExists("kube_pod_container_resource_requests") #New Metric
	if newPrometheus:
		logging.info("Using new Prometheus stats")
	else:
		logging.info("Using old Prometheus stats")
	getConfigDictionary()
	ns_index=0
	#TODO we can iterate of namespaces, but some of the cluster stats will get repeated and summaries get messed up
	namespaceList=list(arg.namespace.split(" "))
	if arg.report or arg.keyReport or arg.cluster or arg.namespaceTotals or arg.nodes or arg.disk or arg.filesystem or arg.pv:
		namespaceList.append("cluster")
	for namespace in namespaceList:
		initNamespace(namespace)
		setupXLSX(namespace, "summary")
		groupingDictionary = generateGrouping(namespace)	
		if namespace in workloadMergeLists:
			workloadMergeList = workloadMergeLists[namespace]
		else:
			workloadMergeList = ""
		for groupingType in groupingDictionary:
			if namespace == "cluster":
				podregexlist = ['.*']
				podnregexlist = ['.*']
			else:
				podregexlist = getPodRegexList(namespace, ns_index, groupingType)
				podnregexlist = getNPodRegexList(namespace, ns_index, groupingType)
			print()
			#logging.info("====================================================================================================================================================================================")
			logging.info("====================================================================================================================================================================================")
			logging.info(getCurrentMemoryUsage() + "main  namespace: " + namespace +  "   groupingType: " + groupingType + "   regex: " + str(podregexlist) + "   nregex: " + str(podnregexlist))	
			setupXLSX(namespace, groupingType)
			defineMetricWorkloadDictionary(groupingType, namespace) 
			runWorkload(groupingType, podregexlist, podnregexlist, namespace, workloadMergeList)
			if groupingType in namesForSummary:
				printSummary(groupingType)		
		logging.prog("----------------------------------------------------------------------------------------------------------------------------------------------------------------")
		logging.prog(getCurrentMemoryUsage() + " Finished exporting Prometheus data to xlsx " )
		ns_index+=1
		if "summary" in workbook:
			logging.prog(getCurrentMemoryUsage() + " Closing workbook[\"summary\"]" )		
			workbook["summary"].close()
			time.sleep(1)
main()
exit()

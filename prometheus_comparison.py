#!/usr/bin/env python3
import pandas as pd
import numpy as np
import logging
import argparse
import textwrap
import sys
import os 
from pathlib import Path
import xlsxwriter
import json
import ast

def init():
	global parser
	parser = argparse.ArgumentParser( prog='prometheus_comparison.py', description=textwrap.dedent('''\
	Compares two or more Prometheus summary files.  
	In the case of two provided comparisons, a difference is generated. 
    In the case of three or more provided comparisons, an average of the summaries is generate.
    The output is a spreadsheet, matching the format of the input summaries.
	'''), 
	epilog=textwrap.dedent('''\
	Example: 
	--dirs promTest1 promTest2 --n cp4waiops --loglevel more'''))
	global keyParser
	keyParser = parser.add_argument_group('KEY arguments')
	global requiredParser
	requiredParser = parser.add_argument_group('REQUIRED arguments')
	setupParser()
	global arg 
	arg = parser.parse_args()
	setupLogging()
	global itemDict 
	itemDict = {}
	global columnDict 
	columnDict = {}
	global sheetDict
	sheetDict = {}
	global summary_files
	summary_files = []
	global excelFiles
	excelFiles = {}
	global runNames 
	runNames = []
	global runTimes
	runTimes = []
def setupParser():
	requiredParser.add_argument(
		"--inputDirs", 
		nargs='+',
		help=("List of derectories with Prometheus exported summary(ies)")
	)
	requiredParser.add_argument(
		"--s",
		"--scope",
		dest='scope',
		help=("Scope to compare summary data for"),
		required=True
	)
	requiredParser.add_argument(
		"--filename",
		help=("filename for output (xlsx will be appended)"),
		required=True
	)
	requiredParser.add_argument(
		"--outputDir", 
		default="",
		help=("Directory to ouput the results to"),
		required=True
	)
	keyParser.add_argument(
		"--loglevel", 
		default="info",
		help=("Logging level: critical, error, warn, warning, info, prog, more, debug, verbose.  Default is info.")
	)
	keyParser.add_argument(
		"--configFile", 
		default="prometheus_comparison_config.json",
		help=("Configuration file path")
	)
	keyParser.add_argument(
		"--cicd", 
		action='store_true',
		help=("If flag is set, script will set Tekton values for sending Slack messages when run in CICD pipeline")
	)
	keyParser.add_argument(
		"--replaceNamespace", 
		default='',
		help=("Replaces 'REPLACE_NAMESPACE' in config file")
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
	logging.basicConfig(level=level, format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S', handlers=[
        logging.FileHandler("perf.log"),
        logging.StreamHandler(sys.stdout)
    ])
	logging.info("logging level: " + str(level))
def searchDirs():
	for dir in arg.inputDirs: 
		if not dir.endswith("/"):
			dir = dir + "/"
		logging.prog("searchDirs  Looking in dir " + dir )
		files = os.listdir(dir)
		for file in files:
			if arg.scope in file and ".summary." in file and not file.startswith("~"):
				logging.more("searchDirs   * " + str(file))
				summary_files.append(dir + file)
				runNames.append(file.split('.')[0])
				runTimes.append(file.split('.')[-2])
			else:
				logging.more("searchDirs     " + str(file))
	x=0
	logging.prog("searchDirs  Found " + str(len(summary_files)) + " matching files")
	for file in summary_files:
		x+=1
		logging.prog("searchDirs  Summary file " + str(x) + " " + str(file))
		excelFiles[file] = {}
		excelFiles[file]["ExcelFile"] = pd.ExcelFile(file)
		loadSheets(file)
def removeHeaderIndents(column):
	return column.replace('\r','').replace('\n', ' ')
def loadSheets(file):
	sheets = excelFiles[file]["ExcelFile"].sheet_names
	excelFiles[file]["sheets"] = {}
	for sheet in sheets:
		logging.more("loadSheets   sheet: " + sheet)
		excelFiles[file]["sheets"][sheet] = pd.read_excel(excelFiles[file]["ExcelFile"], sheet)
		sheetDict[sheet] = {}
def getItems(sheet, df):
	items = df.loc[:,'Item']
	for item in items:
		itemDict[sheet][item] = {}
def getColumns(sheet, df):
	columns = df.columns.values.tolist()
	x=0
	for column in columns:
		if x != 0:
			columnDict[sheet][column] = ""
		else:
			key = ''
			runNum = 0
			for run in runNames:
				key += f'{runNum} = {run} {runTimes[runNum]}'
				if runNum != len(runNames):
					key += '\n'
				runNum += 1
			columnDict[sheet][key] = ""
		x+=1
def buildDefaultSheetContents():
	for sheet in sheetDict:
		itemDict[sheet] = {}
		columnDict[sheet] = {}
		logging.prog("buildDefaultSheetContents  Looking at sheet: " + sheet)
		for file in excelFiles:
			if sheet in excelFiles[file]["sheets"]:
				logging.more("buildDefaultSheetContents   " + file + " has " + sheet)
				getItems(sheet, excelFiles[file]["sheets"][sheet])
				getColumns(sheet, excelFiles[file]["sheets"][sheet])
			else:
				logging.warning("buildDefaultSheetContents  " + file + " does not have " + sheet + ", skipping...")
		if logging.DEBUG >= logging.root.level:
			for item in itemDict[sheet]:
				logging.debug("buildDefaultSheetContents  " + sheet + " item: " + item)
			for column in columnDict[sheet]:
				logging.debug("buildDefaultSheetContents  " + sheet + " column: " + removeHeaderIndents(column))
def iterateOverSheets(fileCount):
	for sheet in sheetDict:
		fileNum = 0
		for file in excelFiles:
			if sheet in excelFiles[file]["sheets"]:
				logging.prog("iterateOverSheets  File: " + file + " Sheet: " + sheet)
				df = excelFiles[file]["sheets"][sheet]
				itemsInSheet = df['Item'].tolist()
				columnsInSheet = df.columns.values.tolist()
				row=-1
				for item in itemDict[sheet]: 
					if item in itemsInSheet:
						row+=1
						logging.more("iterateOverSheets   File: " + file + " Sheet: " + sheet + " item: " + item)
						for column in columnDict[sheet]:
							if column not in itemDict[sheet][item]:
								itemDict[sheet][item][column] = [None] * fileCount
							if column in columnsInSheet:
								value = df.iloc[row][column]
								itemDict[sheet][item][column][fileNum] = value
							logging.verbose("iterateOverSheets  column: " + removeHeaderIndents(column) + "  value " + str(itemDict[sheet][item][column]))
			fileNum+=1
def setupXLSX(name):
	if name:
		xlsxFileName = arg.filename + ".avg" + ".xlsx"
	else:
		xlsxFileName = arg.filename + ".xlsx"
		
	
	if arg.outputDir:
		logging.prog("setupXLSX  Creating directory: " + arg.outputDir)
		Path(arg.outputDir).mkdir(parents=True, exist_ok=True)
		xlsxFileNameFull = arg.outputDir + "/" + xlsxFileName
	else:
		xlsxFileNameFull = xlsxFileName
		
	if os.path.exists(xlsxFileName):
		logging.prog("Removing xlsx file: " + xlsxFileName)
		os.remove(xlsxFileName)
	workbook = xlsxwriter.Workbook(xlsxFileNameFull, {'strings_to_numbers': True})
	formats = {}
	
	formats["textWrap"] = {}
	formats["decimal"] = {}
	formats["integer"] = {}
	formats["percent"] = {}
	
	formats["textWrap"]["standard"] = workbook.add_format({'text_wrap': True})
	formats["decimal"]["standard"] = workbook.add_format({'num_format': '#,##0.000'})
	formats["integer"]["standard"] = workbook.add_format({'num_format': '#,##0'})
	formats["percent"]["standard"] = workbook.add_format({'num_format': '0.00%'})
	
	formats["textWrap"]["right1_boarder"] = workbook.add_format({'text_wrap': True, 'right': 1})
	formats["decimal"]["right1_boarder"] = workbook.add_format({'num_format': '#,##0.000', 'right': 1})
	formats["integer"]["right1_boarder"] = workbook.add_format({'num_format': '#,##0', 'right': 1})
	formats["percent"]["right1_boarder"] = workbook.add_format({'num_format': '0.00%', 'right': 1})
	
	
	return workbook, formats
def printAllValues(fileCount):
	workbook, formats = setupXLSX("")
	avgWorkbook, avgFormats = setupXLSX("avg")
	data = itemDict
	for sheet in sheetDict:
		worksheet = workbook.add_worksheet(sheet)
		worksheet.freeze_panes(1,1)
		worksheet.set_column('A:A', 50)
		
		avgWorksheet = avgWorkbook.add_worksheet(sheet)
		avgWorksheet.freeze_panes(1,1)
		avgWorksheet.set_column('A:A', 50)
		
		columnNum=0
		avgColumnNum=0
		for header in columnDict[sheet]:
			if columnNum == 0:
				worksheet.write(0, columnNum, header, formats["textWrap"]["standard"])	
				columnNum+=1		
				avgWorksheet.write(0, avgColumnNum, header, avgFormats["textWrap"]["standard"])	
				avgColumnNum+=1		
			else:
				fileNum=0
				for file in summary_files:
					fileNum+=1
					worksheet.write(0, columnNum, header + "\n[" + str(fileNum) + "]", formats["textWrap"]["standard"])
					columnNum+=1	
				if fileCount == 2:
					worksheet.write(0, columnNum, header + "\n[Diff]", formats["textWrap"]["right1_boarder"])
					columnNum+=1
				else:				
					worksheet.write(0, columnNum, header + "\n[Avg]", formats["textWrap"]["right1_boarder"])
					columnNum+=1			
				avgWorksheet.write(0, avgColumnNum, header , avgFormats["textWrap"]["standard"])
				avgColumnNum+=1
		rowNum=0
		for item in itemDict[sheet]:
			rowNum+=1
			worksheet.write(rowNum, 0, item)
			avgWorksheet.write(rowNum, 0, item)
			columnNum=0
			avgColumnNum=0
			dkIndex = 0 
			for header in itemDict[sheet][item]:
				dkIndex += 1
				if columnNum > 0: #Skip first column because it is the names, not the data
					values = itemDict[sheet][item][header]
					data[sheet][item][header] = {'values': values}
					total = sum(filter(None,values))
					count = len(list(filter(None,values)))
					if count > 0 :
						avg = total / count
					else:
						avg = 0	
					diff = ""
					if fileCount == 2:
						if count == 2:
							diff = float(values[1]) - float(values[0])						
					formatName="decimal"
					if "(%)" in header:
						formatName="percent"						
					elif "(Mi)" in header or "(int)" in header:
						formatName="integer"
					if logging.DEBUG >= logging.root.level:
						message = "printValues  sheet: {:20s}  item: {:15s}  count: {:2d}  index: {:2d}/{:<2d}   format: {:10s}  header: {:30s}  avg: {:8.2f}   values: {:s}".format(sheet, item, count, rowNum, columnNum, formatName, removeHeaderIndents(header), avg, str(values))
						logging.debug(message)
					x=0
					for file in summary_files:
						try:
							worksheet.write(rowNum, columnNum, values[x], formats[formatName]["standard"])
						except:
							pass
						x+=1
						columnNum+=1							
					if fileCount == 2:
						worksheet.write(rowNum, columnNum, diff, formats[formatName]["right1_boarder"])
						columnNum+=1
					else:			
						try:
							worksheet.write(rowNum, columnNum, avg, formats[formatName]["right1_boarder"])
							data[sheet][item][header]['avg'] = avg
						except:
							pass
						columnNum+=1		
					try:
						avgWorksheet.write(rowNum, avgColumnNum, avg, avgFormats[formatName]["standard"])
					except:
						pass
					avgColumnNum+=1	
				else:
					columnNum+=1
					avgColumnNum+=1	

	analyzeComp(getConfig(), data)

	workbook.close()
	avgWorkbook.close()

def getConfig():
	config = {}
	if os.path.exists(arg.configFile):
		logging.info('Opening configFile ' + arg.configFile)
		with open(arg.configFile) as f:
			data = f.read()
			configTemp = json.loads(data)
				
		for key in configTemp:
			logging.more('Config dictionary: ' + key + " " + str(configTemp[key]))
			config[key] = ast.literal_eval(str(configTemp[key]))
	else:
		logging.error('Configuration file does not exist')
		exit()

	return config

def analyzeComp(config, data):
	slackMsg = ''

	logging.more(f'Analyzing scope {arg.scope}')
	if not arg.scope in config:
		logging.error(f'Scope {arg.scope} not in config file')
		exit()
	for sheetName in config[arg.scope]:
		if sheetName == 'REPLACE_NAMESPACE':
			sheetName = arg.replaceNamespace
		logging.more(f'Checking sheet {sheetName}')
		for statName in config[arg.scope][sheetName]['stats']:
			statNameRep = statName.replace('\n', ' ').replace('  ', ' ')
			logging.more(f'Checking stat {statNameRep}')
			stat = config[arg.scope][sheetName]['stats'][statName]
			comp = stat['comparison']
			thresh = stat['threshold']
			for row in stat['rows']:
				if row == 'REPLACE_NAMESPACE':
					row = arg.replaceNamespace
				logging.more(f'Checking row {row}')
				vals = []
				if row in data[sheetName]:
					vals = data[sheetName][row][statName]["values"]
					prevVal = None
					valCount = 0
					for val in vals:
						if prevVal is not None:
							perDif = 0
							opMsg = None
							if val != prevVal:
								perDif = (abs(val - prevVal) / ((val + prevVal) / 2)) * 100
							if comp == '==':
								if perDif == thresh:
									opMsg = 'equal to'
							elif comp == '!=':
								if perDif != thresh:
									opMsg = 'not equal to'
							elif comp == '>':
								if perDif > thresh:
									opMsg = 'greater than'
							elif comp == '>=':
								if perDif >= thresh:
									opMsg = 'greater than or equal to'
							elif comp == '<':
								if perDif < thresh:
									opMsg = 'less than'
							elif comp == '<=':
								if perDif <= thresh:
									opMsg = 'less than or equal to'

							if opMsg != None:
								msg = f'[{row}] Percent difference {perDif:.2f} between run {valCount - 1} ' \
										f'and {valCount} of {statNameRep} is {opMsg} the threshold {stat["threshold"]}%'
								logging.warning(msg)
								slackMsg += f'[{arg.scope}][{row}] {statNameRep} {prevVal:.2f}->{val:.2f} ({perDif:.2f}) ' \
									f'between run {valCount - 1} and {valCount} {comp} {thresh}%\n'

						prevVal = val
						valCount += 1
				else:
					logging.warning(f'Row \"{row}\" does not exist')

				if len(vals) > 2:
					perDif = 0
					opMsg = None
					if vals[0] != None and vals[-1] != None:
						if vals[0] != vals[-1]:
							perDif = (abs(vals[-1] - vals[0]) / ((vals[-1] + vals[0]) / 2)) * 100
						if comp == '==':
							if perDif == thresh:
								opMsg = 'equal to'
						elif comp == '!=':
							if perDif != thresh:
								opMsg = 'not equal to'
						elif comp == '>':
							if perDif > thresh:
								opMsg = 'greater than'
						elif comp == '>=':
							if perDif >= thresh:
								opMsg = 'greater than or equal to'
						elif comp == '<':
							if perDif < thresh:
								opMsg = 'less than'
						elif comp == '<=':
							if perDif <= thresh:
								opMsg = 'less than or equal to'

						if opMsg != None:
							msg = f'[{row}] Percent difference {perDif:.2f} between first and ' \
								f'last run of {statNameRep} is {opMsg} the threshold {stat["threshold"]}%'
							logging.warning(msg)
							slackMsg += f'[{arg.scope}][{row}] {statNameRep} {vals[0]:.2f}->{vals[-1]:.2f} ({perDif:.2f}) ' \
								f'between first and last run {comp} {thresh}%\n'

	if arg.cicd:
		with open('/tekton/results/comparison-results', 'a+') as f:			
			f.write(slackMsg)
			maxMessageSize = 3000
			if f.tell() > maxMessageSize:
				logging.warning('Slack message too long. Truncating...')
				f.truncate(maxMessageSize)
				largeMsg = 'Too many warnings. Check logs for more information.'
				f.seek(maxMessageSize)
				f.write('...\n' + largeMsg)
				

def main():
	init()
	searchDirs()
	if len(summary_files) < 2: 
		logging.error("main  Only found " + str(len(summary_files)) + " file. 2 or more are required")
		if arg.cicd:
			with open('/tekton/results/comparison-results', 'a+') as f:
				f.write(f'No results found to compare for scope {arg.scope}\n')
		exit()
		
	buildDefaultSheetContents()
	iterateOverSheets(len(summary_files))
	printAllValues(len(summary_files))

try:
	main()
except Exception as err:
	logging.exception(err)
	sys.exit(1)

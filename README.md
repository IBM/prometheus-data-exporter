- [Prometheus Data Exporter](#prometheus-data-exporter)
  * [Introduction](#introduction)
  * [Prereqs](#prereqs)
  * [Token](#token)
  * [Running the script](#running-the-script)
    + [Default Example](#default-example)
    + [Required Arguments](#required-arguments)
    + [Key Optional Arguments:](#key-optional-arguments-)
    + [Metrics:](#metrics-)
    + [Groupings](#groupings)
    + [Regex](#regex)
  * [Data Results](#data-results)
    + [Workbooks](#workbooks)
    + [Worksheets](#worksheets)
- [Prometheus Comparison](#prometheus-comparison)
  * [Running the Script](#running-the-script)
    + [Required Arguments](#required-arguments-1)
    + [Key Arguments](#key-arguments)
  * [Data Results](#data-results-1)
    + [compare..xlsx](#comparexlsx)
    + [compare..avg.xlsx](#compareavgxlsx)

# Prometheus Data Exporter
This tool is designed to export OpenShift 4.x Prometheus data into Xlsx Excel files and raw data reports.  

## Introduction
Prometheus and its data collection enables developers and administrators to have access to weeks of metrics for thousands of metrics, such as: CPU, Memory, Network, and Disk.  Each of these metrics are collected for various levels of the cluster, such as pods, containers, nodes, etc. 
Grafana is extremely useful for visualizing this data.  However, as performance engineers and developers, we often find ourselves needing to export the Prometheus data for various reasons: historical collection for long term comparisons, reports, custom graphs or analysis, data manipulation in Excel, etc.  

## Prereqs
The script is written in Python 3 code. 
The additional libraries `requests` and `xlsxwriter` are required.  
The only known limitation is the `psutil` library may not be easily available on RHEL 7 systems. The script will handle the missing dependency and simply not display memory usage statistics if not found. 
```
yum install python3.8 -y
pip3.8 install requests
pip3.8 install xlsxwriter
pip3.8 install psutil
```

## Token
In order to access a secure OpenShift Prometheus, a token is required. The following bash example will generate and store the token, which can then be passed as an argument to the script. The proper hostname is also required.
```
PROM_HOST=`oc get routes prometheus-k8s -n openshift-monitoring -ojson |jq ".status.ingress"|jq ".[0].host"|sed 's/"//g' `
TOKEN_NAME=`oc get secret -n openshift-monitoring|awk '{print $1}'|grep prometheus-k8s-token -m 1`
PROM_TOKEN=`oc describe secret $TOKEN_NAME -n openshift-monitoring|grep "token:"|cut -d: -f2|sed 's/^ *//g'`
echo $PROM_TOKEN >/tmp/token
echo -e "PROM_HOST $PROM_HOST\nTOKEN_NAME $TOKEN_NAME\nPROM_TOKEN $PROM_TOKEN"
```

## Running the script
There are many different usages and ways to view and aggregate the data. For the most recent information, please see the --help section of the script.

### Default Example
The basic data view that most users will want to start with is the --keyReport flag. This covers getting all of the metrics and groupings of data that most users will need. Further options and details are below. There are also required arguments detailed below.

```
./prometheus_exporter.py --keyReport --n "openshift-namespace" --url $PROM_HOST --start=20210414160000 --end=20210414161000 --tknfile /tmp/token --dir /tmp/outputDir --filename testABC1 --loglevel prog
```

### Required Arguments
```
REQUIRED arguments:
  --n NAMESPACE, --namespace NAMESPACE
                        Namespace to gather detailed data for
  --url URL             URL of the prometheus server
  --tknfile TKNFILE     File with the token in it (either this or the token
                        string --token are required)
  --start START         Start time for range query in UTC, format
                        20210514180000 or 2021-05-14T18:00:00 or
                        2021-05-14T18:00:00.000Z
  --end END             End time for range query in UTC, format 20210514180000
                        or 2021-05-14T18:00:00 or 2021-05-14T18:00:00.000Z
```

### Key Optional Arguments:
Default logging is info, which should display minimal output on a working run. Use --loglevel prog for "progress" if you would like to see basic progress activity.
```
KEY arguments:
  --loglevel LOGLEVEL   Logging level: critical, error, warn, warning, info,
                        prog, more, debug, verbose. Default is info.
  --dir DIR             Directory to store the results in
  --filename FILENAME   Additional string to add to output filename
  --cfgFile CFGFILE     Filename of the dictionary of dictionaries with
                        analysis configuration. If not specified, will look
                        for prometheus_exporter_config.json and then
                        config.json. If not found, default settings internal
                        to the script are used.
  --step STEP           Step (in seconds only) for range query, default is 30
  --printSummary        Print the summary data to screen.
  --printAnalysis       Print the analysis of the data to screen.
  --keyReport           Return all key data (pod and container details and
                        summary, namespaces, nodes, filesystems; uses
                        keyMetrics)
  --report              Return all known data
```
Example:
```
--loglevel prog --dir /temp/promTest1 --filename testname --step 60 --keyReport --printSummary --printAnalysis
```

### Metrics:
There are various metrics that can be selected a la carte, or in groups. The --keyMetrics flag is what you'll usually need (excludes some of the extra CPU stats) but those can be appended as well. Note, --keyReport will include --keyMetrics automatically.
```
METRIC arguments:
  --rate RATE           Step for range query, default is 5m
  --cpu                 Return total CPU usage data using the pre-rated metric
  --cpur                Return total CPU usage data using the custom rate
  --cpuUser             Return CPU user usage data
  --cpuSys              Return CPU system usage data
  --throttle            Return CPU throttle data
  --allCpu              Return data for all CPU metrics
  --rss                 Return RSS memory data
  --wss                 Return WSS memory data
  --cache               Return cache memory data
  --memUse              Return total memory usage data
  --allMem              Return data for all memory metrics
  --reqlim              Return data for requests and limits
  --network             Return data for network usage (not available at
                        container level)
  --keyMetrics          Return data for all key metrics (count, req/lim, CPUr,
                        RSS, WSS, Cache, memUse, RX/TX)
  --allMetrics          Return data for all known metrics
```

### Groupings
The script can collect various groupings of the data. By default you get the pod and/or container level details, or raw data. These can be grouped into summaries for all pods/containers of the same type with --sum or --avg. For example, if you have 3 Kafka pods, --sum will give you the total summation of the usage by all 3 Kafka pods. Same for --avg (although this may or may not be very useful). Individual pods can be included or excluded with the --regex or --nregex (negative regex). Note, be sure to include .* where appropriate. Finally, there are "report" flags which can be used to automatically select multiple datasets.
```
GROUPING arguments:
  --namespaceTotals     Display details at the namespace level
  --nodes               Display node details
  --disk                Display disk details
  --filesystem          Display filesystem details
  --pv                  Display persistent volume details
  --cluster             Display details at the cluster (namespaceTotals,
                        nodes, disk, filesystem, pvs)
  --pod                 Display pod level details
  --container           Display container level details
  --sum                 Sum the details into a single result set by category
  --avg                 Average the details into a single result set by
                        category
  --noDetail            Do not display the detailed breakdown
```
Example, returns pod details and pod summations:
```
--pod --sum
```
Example, returns pod and container summations without the large detailed breakdown:
```
--pod --container --sum --noDetail
```

### Regex
Regular expressions can be used to include or exclude certain pods.
```
REGEX arguments:
  --regex REGEX         Regex for pod(s) to include, default is all or ".*"
  --nregex NREGEX       Negative Regex for pod(s) to exclude, default is no
                        exclusions
```
Example, return pod and container details and summations for all keyMetrics for all kafka and cassandra pods:
```
--keyReport --regex ".*kafka.*|.*cassandra.*"
```

## Data Results
### Workbooks
Each grouping category gets its own workbook to separate the data. You may have a workbook for pod details, pod summation, container details, container summation, cluster wide statistics, averages etc.

### Worksheets
By default, each metric selected gets its own worksheet in the resulting .xlsx file. For example, a worksheet for "rss", a worksheet for "wss" etc. The exception are the requests and limits.
There are also "All-CPU", "All-Mem", "All-Net" sheets created where all of the appropriate metrics are also stored, grouped by workload/pod/container. This allows for grouped graphs and views of all related metrics, as well as views by metric type. The requests and limits are only displayed on the "All-" sheets.

# Prometheus Comparison
The `prometheus_exporter.py` focuses on exporting and analyzing the data of a single time period. 
Once you have multiple test runs or time period results, the next step is to compare these results in a single report. 
The `prometheus_comparison.py` script is used for this purpose, aggregating the multiple runs' data into a single set of files.  

## Running the Script
### Required Arguments
```
REQUIRED arguments:
  --dirs DIRS [DIRS ...]
                        List of directories with Prometheus exported summary(ies)
  --n NAMESPACE, --namespace NAMESPACE
                        Namespace to compare summary data for
```
The `--dir` flag is a list of one or more directories you want to look for .summary. files in. The `--n namespace` flag specifies what namespace (or "cluster") to look at. For example, in this case I have a single directory `prom_long_run_staged` with 6 test results in it. The `product-namespace.summary` files are grabbed within the dir. Note, other files are in the folder.
```
python 3.8 prometheus_comparison.py --dir prom_long_run_staged --n product-namespace --loglevel prog
2021-08-16 15:17:51 INFO     logging level: 19
2021-08-16 15:17:51 PROG     Script version: 1.0.1 20210816
2021-08-16 15:17:51 PROG     searchDirs  Looking in dir prom_long_run_staged/
2021-08-16 15:17:51 PROG     searchDirs  Found 6 matching files
2021-08-16 15:17:51 PROG     searchDirs  Summary file 1 prom_long_run_staged/test1.product-namespace.summary.202107300000-202107300100.xlsx
2021-08-16 15:17:51 PROG     searchDirs  Summary file 2 prom_long_run_staged/test2.product-namespace.summary.202107300700-202107300800.xlsx
2021-08-16 15:17:52 PROG     searchDirs  Summary file 3 prom_long_run_staged/test3.product-namespace.summary.202107300800-202107300900.xlsx
2021-08-16 15:17:52 PROG     searchDirs  Summary file 4 prom_long_run_staged/test4.product-namespace.summary.202107301100-202107301203.xlsx
2021-08-16 15:17:53 PROG     searchDirs  Summary file 5 prom_long_run_staged/test5.product-namespace.summary.202107301203-202107301500.xlsx
2021-08-16 15:17:53 PROG     searchDirs  Summary file 6 prom_long_run_staged/test6.product-namespace.summary.202107301603-202107302000.xlsx
```

### Key Arguments
Optionally, you may specify the log level and output directory. If the --outputDir is not specified, the results go to the current directory.
```
KEY arguments:
  --loglevel LOGLEVEL   Logging level: critical, error, warn, warning, info, prog, more, debug, verbose. Default is info.
  --outputDir OUTPUTDIR
                        Directory to output the results to
```

## Data Results
There are 2 results files generated: `compare.<namespace>.xlsx` and `compare.<namespace>.avg.xlsx`.

### compare..xlsx
This file has the raw results of the 2 or more comparison files with [1] [2] [3] etc appended to the headers. For example:
```
"cpuReq avg (cores) [1]"
"cpuReq avg (cores) [2]"
"cpuReq avg (cores) [3]"
```
There is also an [Avg] header with the average of all of the 2 or more input summary files. If there are only 2 comparison files, there is a [Diff] result, subtracting the second result from the first.
```
"cpuReq avg (cores) [Avg]"
"cpuReq avg (cores) [Diff]"
```
### compare..avg.xlsx
This file is the ONLY the averages of the 2 or more input summary files. The file should look exactly like the inputs (same column headers and rows) just with the averages as the values.
The purpose of this file would be to generate a baseline. For example, you run 10 BVT test runs where you expect the results to be the same or very similar. The averages would be able to be used to compare to subsequent runs to see if things start to deviate from the baseline.

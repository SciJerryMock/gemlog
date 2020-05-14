## gemlog changes:
## new gps column (time)
## metadata time format change

## known potential problems:
## missing/repeated samples at block boundaries due to InterpGem at the beginning
## bitweight missing in output mseed
## not starting files on the hour
## doesn't handle nearly-empty raw files well

## fixed issues:
## from gemlog ReadGemv0.85C (and others too): NaNs in L$gps due to unnecessary and harmful doubling of wna indexing. Also, added python code to drop NaNs.
import rpy2
import rpy2.robjects.packages as rpackages
import obspy
import numpy as np
from numpy import NaN, Inf
import os, glob
import pandas as pd
import pdb
import matplotlib.pyplot as plt
gemlogR = rpackages.importr('gemlog')
#####################
def Convert(rawpath = '.', convertedpath = 'converted', metadatapath = 'metadata', metadatafile = '', gpspath = 'gps', gpsfile = '', t1 = -Inf, t2 = Inf, nums = NaN, SN = '', bitweight = NaN, units = 'Pa', time_adjustment = 0, blockdays = 1, fileLength = 3600, station = '', network = '', location = ''):
    print('gemlog_python_backup')
    ## bitweight: leave blank to use default (considering Gem version, config, and units). This is preferred when using a standard Gem (R_g = 470 ohms)
    
    ## make sure the raw directory exists and has real data
    assert os.path.isdir(rawpath), 'Raw directory ' + rawpath + ' does not exist'
    assert len(glob.glob(rawpath + '/FILE' +'[0-9]'*4 + '.???')) > 0, 'No data files found in directory ' + rawpath

    ## make sure bitweight is a scalar
    if((type(nums) == type(1)) or (type(nums) == type(1.0))):
        nums = np.array([nums])
    else:
        nums = np.array(nums)

    ## if 'nums' is default, convert all the files in this directory
    if((len(nums) == 0) or np.isnan(nums[0])):
        if(True or len(SN) == 1): # trying to check that SN is a scalar
            fn = glob.glob(rawpath + '/FILE' +'[0-9]'*4 + '.' + SN) + \
                 glob.glob(rawpath + '/FILE' +'[0-9]'*4 + '.TXT')
        else:
            fn = glob.glob(rawpath + '/FILE' +'[0-9]'*4 + '.???')
        nums = np.array([int(x[-8:-4]) for x in fn]) # "list comprehension"
    nums.sort()

    ## start at the first file in 'nums'
    n1 = np.min(nums)
  
    ## read the first set of up to (24*blockdays) files
    L = NewGemVar()
    while((L['data'].count() == 0) & (n1 <= max(nums))): ## read sets of files until we get one that isn't empty
        nums_block = nums[(nums >= n1) & (nums < (n1 + (12*blockdays)))] # files are 2 hours, so 12 files is 24 hours
        L = ReadGemPy(nums_block, rawpath, alloutput = False, requireGPS = True, SN = SN, units = 'counts', time_adjustment = time_adjustment, network = network, station = station, location = location, output_int32 = True) # request data in counts so it can be written to segy as ints. conversion to physical units is provided as a header element in the file.
    
        n1 = n1 + (12*blockdays) # increment file number counter

    p = L['data']
    
    ## if bitweight isn't set, use the default bitweight for the logger version, config, and units
    if(np.isnan(bitweight)):
        if(units == 'Pa'):
            bitweight = L['header']['bitweight_Pa'][0]
        elif(units == 'V'):
            bitweight = L['header']['bitweight_V'][0]
        elif (units == 'Counts' | units == 'counts'):
            bitweight = 1
      
    ## if not specified, define t1 as the earliest integer-second time available
    if(np.isinf(float(t1))):
        t1 = L['data'].stats.starttime
        t1 = obspy.core.UTCDateTime(np.ceil(float(t1)))
        #t1 = trunc(t1) + 1 

    if(np.isinf(float(t2))):
        t2 = obspy.core.UTCDateTime.strptime('9999-12-31 23:59:59', '%Y-%m-%d %H:%M:%S') # timekeeping apocalypse
  
    wsn = 0
    while(len(SN) < 3): # take the first non-NA SN. This is important because there can be blank files in there.
        wsn = wsn+1
        SN = L['header']['SN'][wsn]
  
    ## set up the gps and metadata files. create directories if necessary
    if(len(gpsfile) == 0):
        if(not os.path.isdir(gpspath)):
            os.makedirs(gpspath) # makedirs vs mkdir means if gpspath = dir1/dir2, and dir1 doesn't exist, that dir1 will be created and then dir1/dir2 will be created
        gpsfile = makefilename(gpspath, SN, 'gps')

  
    if(len(metadatafile) == 0):
        if(not os.path.isdir(metadatapath)):
            os.makedirs(metadatapath)
        metadatafile = makefilename(metadatapath, SN, 'metadata')
  
    ## if the converted directory does not exist, make it
    if(not os.path.isdir(convertedpath)):
        os.makedirs(convertedpath)
  
    ## start metadata and gps files
    metadata = L['metadata']   
    gps = L['gps']
    metadata.to_csv(metadatafile, index=False) ## change to metadata format. need to make ScanMetadata compatible with both

    wgps = (gps['t'] > (t1 - 1)) ## see ReadGemPy to get gps.t working. update gemlog accordingly.
    if(len(wgps) > 0):
        gps[wgps].to_csv(gpsfile, index=False)

    #print('t1: ' + str(t1))
    #print('p.stats.starttime: ' + str(p.stats.starttime))
    #print('writeHour: ' + str(writeHour))
    #print('writeHourEnd: ' + str(writeHourEnd))
    writeHour = max(t1, p.stats.starttime)
    writeHour = WriteHourMS(p, writeHour, fileLength, bitweight, convertedpath)
    
    ## read sets of (12*blockdays) files until all the files are converted
    while(True):
        ## check to see if we're done
        if(n1 > np.max(nums)):# & len(p) == 0):
            break # out of raw data to convert
        if((t1 > t2) & (not np.isnan(t1 > t2))):
            break # already converted the requested data
        ## load new data if necessary
        tt2 = min(t2, truncUTC(t1, 86400*blockdays) + 86400*blockdays)
        #print([tt2, n1, nums, SN])
        while((p.stats.endtime < tt2) & (n1 <= max(nums))):
            #pdb.set_trace()
            L = ReadGemPy(nums[(nums >= n1) & (nums < (n1 + (12*blockdays)))], rawpath, alloutput = False, requireGPS = True, SN = SN, units = 'counts', network = network, station = station, location = location, output_int32 = True)
            #pdb.set_trace()
            if(len(L['data']) > 0):
                p = p + L['data']   
            #print(p)
            n1 = n1 + (12*blockdays) # increment file counter
            if(len(L['data']) == 0):
                next # skip ahead if there aren't any readable data files here
                
            ## process newly-read data
            if(any(L['header'].SN != SN) | any(L['header'].SN.apply(len) == 0)):
                w = (L['header'].SN != SN) | (L['header'].SN.apply(len) == 0)
                print('Wrong or missing serial number(s): ' + L['header'].SN[w] + ' : numbers ' + str(nums[np.logical_and(nums >= n1, nums < (n1 + (12*blockdays)))][w]))
            
            ## update the metadata file
            metadata.to_csv(metadatafile, index=False, mode='a', header=False)
            
            ## update the gps file
            if(len(wgps) > 0):
                gps.to_csv(gpsfile, index=False, mode='a', header=False)
                
        ## run the conversion and write new converted files
        #if((pp.stats.endtime >= t1) & (pp.stats.starttime <= tt2))):
        while((writeHour + fileLength) <= p.stats.endtime):
            writeHour = WriteHourMS(p, writeHour, fileLength, bitweight, convertedpath)
            
        ## update start time to convert
        p.trim(writeHour, t2)
        t1 = truncUTC(tt2+(86400*blockdays) + 1, 86400*blockdays)
    ## while True
    ## done reading new files. write what's left and end.
    while((writeHour <= p.stats.endtime) & (len(p) > 0)):
        writeHour = WriteHourMS(p, writeHour, fileLength, bitweight, convertedpath)
        p.trim(writeHour, t2)

def WriteHourMS(p, writeHour, fileLength, bitweight, convertedpath, writeHourEnd = np.nan):
    if(np.isnan(writeHourEnd)):
        writeHourEnd = truncUTC(writeHour, fileLength) + fileLength
    pp = p.copy()
    pp.trim(writeHour, writeHourEnd)
    pp.stats.calib = bitweight
    fn = MakeFilenameMS(pp)
    pp = pp.split() ## in case of data gaps ("masked arrays", which fail to write)
    if(len(pp) > 0):
        pp.write(convertedpath +'/'+ fn, format = 'MSEED', encoding=10) # encoding 10 is Steim 1
    writeHour = writeHourEnd
    return writeHour
    
## DONE
####################################
## test command
#rawpath = '/home/jake/Work/Gem_Tests/2019-05-29_RoofTestIsolation/raw/'
#SN = '051'
#Convert(rawpath = rawpath, SN = SN, nums = range(14, 15)) 
#Convert(rawpath = rawpath, SN = SN, nums = range(6,8))
#4,15; 5,15; 6,8; 8,10; :ValueError: cannot convert float NaN to integer
#10,12: no error

####################################

def truncUTC(x, n=86400):
    return obspy.core.UTCDateTime(int(float(x)/n)*n)#, origin='1970-01-01')

def makefilename(dir, SN, dirtype):
    n = 0
    fn = dir + '/' + SN + dirtype + '_'+ f'{n:03}' + '.txt'
    while(os.path.exists(fn)):
        n = n + 1
        fn = dir + '/' + SN + dirtype + '_' + f'{n:03}' + '.txt'

    return fn


def MakeFilenameMS(pp):
    t0 = pp.stats.starttime
    return f'{t0.year:04}' + '-' +f'{t0.month:02}' + '-' +f'{t0.day:02}' + 'T' + f'{t0.hour:02}' + ':' + f'{t0.minute:02}' + ':' + f'{t0.second:02}' + '.' + pp.id + '.mseed'
#import pdb

def ReadGemPy(nums = np.arange(10000), path = './', SN = str(), units = 'Pa', bitweight = np.NaN, bitweight_V = np.NaN, bitweight_Pa = np.NaN, alloutput = False, verbose = True, requireGPS = False, time_adjustment = 0, network = '', station = '', location = '', output_int32 = False):
    emptyGPS = pd.DataFrame.from_dict({'year':np.array([]), 
                                      'date':np.array([]), 
                                      'lat':np.array([]), 
                                      'lon':np.array([]), 
                                      't':np.array([])})
    if(len(station) == 0):
        station = SN
    L = gemlogR.ReadGem([float(x) for x in nums], path, SN, units, float(bitweight), float(bitweight_V), float(bitweight_Pa), alloutput, verbose, requireGPS)
    #pdb.set_trace()
    dataGood = True
    timingGood = True
    ## verify that ReadGem output is good
    if(type(L) == rpy2.rinterface.NULLType): #if it's null, flag it
        dataGood = False
        timingGood = False
    elif((len(L[0]) == 0) | np.isnan(np.sum(L[0]))): # if it's missing GPS data, flag it
        timingGood = False
        LI = L
    else:
        ## try interpolating the time, which may fail
        try:    
            LI = gemlogR.InterpTime(L)
        except:
            timingGood = False
            LI = L
        
    #pdb.set_trace()
    if((not dataGood) | ((not timingGood) & requireGPS)): # if no timing info, return nothing
        data = np.array([])
        if(output_int32):
            data = np.array(data.round(), dtype = 'int32') ## apparently int32 is needed for steim1
        tr = obspy.Trace(data)
        tr.stats.station = station
        tr.stats.location = location # this may well be ''
        tr.stats.channel = 'HDF' # Gem is always HDF
        tr.stats.delta = 0.01
        tr.stats.network = network # can be '' for now and set later
        tr.stats.starttime = obspy.core.UTCDateTime(0)

        gps = emptyGPS
        metadata = pd.DataFrame.from_dict({'millis':[], 'maxWriteTime':[], 'minFifoFree':[], 
                                           'maxFifoUsed':[], 'maxOverruns':[], 'gpsOnFlag':[],
                                           'unusedStack1':[], 'unusedStackIdle':[], 't':[]})
        output = {'data': tr,
                  'metadata': metadata,
                  'gps': gps,
                  'header': pd.DataFrame.from_dict({'SN':[SN],'bitweight_Pa':[np.NaN], 'bitweight_V':[np.NaN]})
                  }   
        return output
    
    header1=pd.DataFrame.from_dict({ key : np.asarray(L[2].rx2(key)) for key in L[2].names[0:-1] }) # normal header
    header2=pd.DataFrame.from_dict({ key : np.asarray(L[2][-1].rx2(key)) for key in L[2][-1].names }) # config
    header = pd.concat([header1, header2], axis=1, sort=False)
          
    metadata = pd.DataFrame.from_dict({ key : np.asarray(L[3].rx2(key)) for key in L[3].names })
    metadata.millis = metadata.millis.apply(int)
    metadata.maxWriteTime = metadata.maxWriteTime.apply(int)
    metadata.minFifoFree = metadata.minFifoFree.apply(int)
    metadata.maxFifoUsed = metadata.maxFifoUsed.apply(int)
    metadata.maxOverruns = metadata.maxOverruns.apply(int)
    metadata.gpsOnFlag = metadata.gpsOnFlag.apply(int)
    metadata.unusedStack1 = metadata.unusedStack1.apply(int)
    metadata.unusedStackIdle=metadata.unusedStackIdle.apply(int)
    
    if(timingGood):
        metadata.t=metadata.t.apply(obspy.core.UTCDateTime)
        gps = pd.DataFrame.from_dict({ key : np.asarray(L[4].rx2(key)) for key in L[4].names })
        gps=gps.dropna() # ignore rows containing NaNs to avoid conversion errors
        gps.year = gps.year.apply(int)
        year = gps.year
        hour = (24*(gps.date % 1))
        minute = (60*(hour % 1))
        second = (60*(minute % 1))
        ts=year.apply(str) + ' ' + gps.date.apply(int).apply(str) + ' ' + hour.apply(int).apply(str) + ':' + minute.apply(int).apply(str) + ':' + second.apply(int).apply(str)
        t = pd.Series(ts.apply(obspy.core.UTCDateTime.strptime, format='%Y %j %H:%M:%S') + (second % 1))
        t.name='t'
        gps = gps.join(t)
    else:
        metadata.t = (metadata.millis/1000).apply(obspy.core.UTCDateTime)
        gps = emptyGPS
        
    data = np.array(LI[1]) # p
    if(output_int32):
        data = np.array(data.round(), dtype = 'int32') ## apparently int32 is needed for steim1
    tr = obspy.Trace(data)
    tr.stats.delta = 0.01
    tr.stats.network = network # can be '' for now and set later
    if(timingGood):
        tr.stats.starttime = LI[0][0] + time_adjustment
    else:
        tr.stats.starttime = obspy.core.UTCDateTime(0)

    if(len(station) == 0): # have to have a station; assume SN if not given
        print(header.SN)
        wsn = 0
        while(True):
            tr.stats.station = header.SN[wsn]
            wsn = wsn + 1
            if((wsn >= len(header.SN)) | (len(tr.stats.station) >= 3)):
                break
    else:
        tr.stats.station = station
    tr.stats.location = location # this may well be ''
    tr.stats.channel = 'HDF' # Gem is always HDF

    output = {'data': tr,
              'metadata': metadata,
              'gps': gps,
              'header': header
    }
    return output

def NewGemVar():
    tr = obspy.Trace()
    tr.stats.delta = 0.01
    gps = pd.DataFrame(columns=['year', 'date', 'lat', 'lon'])
    metadata = pd.DataFrame(columns=['millis', 'batt', 'temp', 'A2', 'A3', \
                                     'maxWriteTime', 'minFifoFree', 'maxFifoUsed', \
                                     'maxOverruns', 'gpsOnFlag', 'unusedStack1',\
                                     'unusedStackIdle', 't'])
    output = {'data': tr,
              'metadata': metadata,
              'gps': gps
    }
    return output


def MakeDB(path, pattern = '*', savefile = './DB.csv'):
    #path = 'mseed'
    #pattern = '*'
    files = glob.glob(path + '/' + pattern)
    files.sort()
    DB = []
    count = 0
    for file in files:
        tr = obspy.read(file)[0]
        maxVal = tr.data.max()
        minVal = tr.data.min()
        tr.detrend('linear')
        tr.filter('highpass', freq=0.5)
        amp_HP = tr.std()
        row = pd.DataFrame([[file, tr.stats.station, tr.stats.location, amp_HP, maxVal, minVal, tr.stats.starttime, tr.stats.endtime]], columns = ['filename', 'station', 'location', 'amp_HP', 'max', 'min', 't1', 't2'])
        DB.append(row)
        if((count % 100) == 0):
            print(str(count) + ' of ' + str(len(files)))
        count = count + 1
    DB = pd.concat(DB)
    DB.to_csv(savefile)
    return(DB)

def CalcStationStats(DB, t1, t2):
    import obspy, glob
    import pandas as pd
    from obspy import UTCDateTime as T
    #t1 = '2020-04-14'
    #t2 = '2020-04-24T20:00:00'
    t1 = obspy.core.UTCDateTime(t1)
    t2 = obspy.core.UTCDateTime(t2)
    numHour = (t2 - t1)/3600.0
    DB.t1 = DB.t1.apply(T)
    DB.t2 = DB.t2.apply(T)
    DB.goodData = (DB.amp_HP > 0.5) & (DB.amp_HP < 2e4) & ((DB.t2 - DB.t1) > 3598) & ((DB.t2 - DB.t1) < 3602)
    DB.anyData = (DB.amp_HP > 0) 
    out = []
    for sta in DB.station.unique():
        w = np.where((DB.station == sta) & (DB.t1 > t1) & (DB.t2 < t2))[0]
        if(len(w) == 0):
            continue
        else:
            q1 = np.quantile(np.array(DB.amp_HP)[w], 0.25)
            q3 = np.quantile(np.array(DB.amp_HP)[w], 0.75)
            out.append(pd.DataFrame([[sta, np.sum(np.array(DB.goodData)[w])/numHour, np.sum(np.array(DB.anyData)[w])/numHour, q1, q3]], columns = ['station', 'goodData', 'anyData', 'q1', 'q3']))
    out = pd.concat(out)
    return(out)

def PlotAmp(DB):
    allSta = DB.station.unique()
    allSta.sort()
    for sta in DB.station.unique():
        w = np.where(DB.station == sta)[0]
        w.sort()
        plt.plot(DB.t1[w], np.log10(DB.amp_HP[w]), '.')
        print(str(sta) + ' ' + str(np.quantile(DB.amp_HP[w], 0.25)))
    plt.legend(allSta)
    plt.show()

## 55 (3.03), 84 (4.37), 108 (2.04), 49 (1.78), others (1.3-1.6)

#L55=gemlog.ReadGemPy(nums=np.arange(6145,6151),SN='055', path = 'raw')
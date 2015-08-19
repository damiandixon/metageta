# -*- coding: utf-8 -*-
# Copyright (c) 2015 Australian Government, Department of the Environment
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

'''
Metadata driver for ENVI imagery
'''

format_regex=[r'\.hdr$']
'''Regular expression list of file formats'''

#import base dataset modules
#import __dataset__
import __default__

# import other modules
import sys, os,glob
from metageta.overviews import GetDataTypeRange
from osgeo import gdal

class Dataset(__default__.Dataset): 
    '''Subclass of __default__.Dataset class so we get a load of metadata populated automatically'''
    def __init__(self,f=None):
        if not f:f=self.fileinfo['filepath']
        if f[:4]=='/vsi':raise NotImplementedError
        
        lin=open(f).readline().strip() #read first line, is it an ENVI format hdr...?
        if lin != 'ENVI':raise NotImplementedError
        
        dat=os.path.splitext(f)[0]
        self._datafile=''
        if os.path.exists(dat):self._datafile=dat
        else:  #Handle ENVI files with _any_ extension
            for f in glob.glob(dat+'.*'):
                ds=gdal.Open(f)
                if ds and ds.GetDriver().ShortName:
                    self._datafile=f
                    break
                del ds

        if not self._datafile: 
            raise NotImplementedError #This error gets ignored in __init__.Open()

    def __getmetadata__(self):
        '''Read Metadata for a ENVI image as GDAL doesn't work if you pass the header file...'''
        try:__default__.Dataset.__getmetadata__(self, self._datafile) #autopopulate basic metadata
        except IOError,err:               #Handle the odd ENVI files held by SSD
            hdr=self.__parseheader__()    #"file type = ENVI" instead of "file type = ENVI standard"
            if hdr['file type']=='ENVI':  #I assume they were generated by some external software

                #make a dummy hdr with a dummy 1 byte image file
                import tempfile,geometry,shutil

                tmpd=tempfile.mkdtemp(prefix='gdal')
                tmph=open(tmpd+'/dummy.hdr','w')
                tmpf=open(tmpd+'/dummy','wb')
                hdr['file type']+=' Standard'
                tmph.write('ENVI\n')
                for key in hdr:
                    if '\n' in hdr[key]:tmph.write(key+' = {'+hdr[key]+'}\n')
                    else: tmph.write(key+' = '+hdr[key]+'\n')
                tmph.close()
                tmpf.write('\x00\x00')
                tmpf.close()
                __default__.Dataset.__getmetadata__(self, tmpd+'/dummy')
                del self._gdaldataset
                shutil.rmtree(tmpd, ignore_errors=True)

                #Make a VRT
                md=self.metadata
                byteorder={'':None,'0':'LSB','1':'MSB'}
                byteorder=byteorder[hdr.get('byte order','')]
                min=GetDataTypeRange(gdal.GetDataTypeByName(md['datatype']))[0]
                nodata=hdr.get('data ignore value',str(min))
                if hdr.get('interleave','').upper()=='BSQ':
                    vrt=geometry.CreateBSQRawRasterVRT(self._datafile,md['nbands'],md['cols'],md['rows'],md['datatype'],nodata,headeroffset=0,byteorder=byteorder,relativeToVRT=0)
                elif hdr.get('interleave','').upper()=='BIP':
                    vrt=geometry.CreateBIPRawRasterVRT(self._datafile,md['nbands'],md['cols'],md['rows'],md['datatype'],nodata,headeroffset=0,byteorder=byteorder,relativeToVRT=0)
                else:#Assume bil
                    vrt=geometry.CreateBILRawRasterVRT(self._datafile,md['nbands'],md['cols'],md['rows'],md['datatype'],nodata,headeroffset=0,byteorder=byteorder,relativeToVRT=0)

                self._gdaldataset=geometry.OpenDataset(vrt)
                #Fix for Issue 17
                for i in range(1,self._gdaldataset.RasterCount+1):
                    self._gdaldataset.GetRasterBand(i).SetNoDataValue(nodata)

                pass
                
            else:raise #not the dodgy SSD files, re-raise the orig. error
            
    def __parseheader__(self):
        hdr=open(self.fileinfo['filepath']).readlines()
        md={}
        i=1 #Skip the ENVI line
        while True: #Extract all keys and values from the header file into a dictionary
            line=hdr[i].strip()
            if line.find('{') > -1:
                var=[s.strip() for s in line.replace('{','').split('=',1)]
                if line.find('}') == -1:
                    i+=1
                    while True:
                        line=hdr[i].strip()
                        var[1] += '\n'+line
                        if line.find('}') > -1:break
                        i+=1
                var[1]=var[1].replace('}','')
            else:var=[s.strip() for s in line.split('=',1)]
            md[var[0]]=var[1]
            i+=1
            if i >=len(hdr):break
        return md

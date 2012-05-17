import web
import Image
import ImageOps
import os.path
import os
import math
import sys
import json
from random import Random

testRun = os.getenv( "PLACEMANUL_TEST" )
directoryRoot = "." if testRun else "/var/www/placemanul"
urlRoot = ""

sourceDir = directoryRoot + "/source/"
cachedDir = directoryRoot + "/static/"
templateDir = directoryRoot + "/templates/"

if testRun:
    print >> sys.stderr, "Directory root:", directoryRoot
    print >> sys.stderr, "Source directory:", sourceDir
    print >> sys.stderr, "Cached directory:", cachedDir
    print >> sys.stderr, "Template directory:", templateDir

render = web.template.render( templateDir )

urls = (
    '/(attribution|index|about)/?', 'serve_page',
    '/?', 'index',
    '/(.+)', 'serve_image',
)

class Manul:
    def __init__(self, number = None, filename = None, author = "", license = "", attribution_link = "", nominal_size = None, region = None):
        assert number
        assert filename
        self.number = int(number)
        self.filename = filename
        self.author = author
        self.license = license
        self.attribution_link = attribution_link
        self.region = region
        self.nominal_size = nominal_size
        img = Image.open( sourceDir + filename )
        self.actual_size = ax, ay = img.size
        if nominal_size and region:
            nx, ny = nominal_size
            wr, hr = ax/float(nx), ay/float(ny)
            ((rx,ry),(rw,rh)) = self.region
            rx *= wr
            ry *= hr
            rw *= wr
            rh *= hr
            self.region = ((rx,ry),(rx+rw-1,ry+rh-1))
        self.width, self.height = self.actual_size
        self.aspect = self.width / float( self.height )

def loadManul( key, j ):
    return Manul( number = int(key),
                  filename = j[u"image"],
                  author = j.get(u"author") or "",
                  attribution_link = j.get(u"attribution_link") or "",
                  license = j.get(u"license") or "",
                  nominal_size = j.get(u"size"),
                  region = j.get(u"region") )

def findfiles():
    jsonFile = sourceDir + "manuls.json"
    with open( jsonFile, "r" ) as f:
        rv = [ loadManul( key, record ) for key, record in json.load( f ).items() ]
    return dict( map( lambda r : (r.number, r), rv ) )

manuls = findfiles()

def map_option( option ):
    if option in ("grayscale", "gray", "greyscale", "grey", "g"):
        return "g"
    if option in ("sepia", "s"):
        return "s"
    if option in ("negative", "n"):
        return "n"
    return None

def filename( name, w, h, optionString ):
    return "%s-%s-%dx%d.jpeg" % (name, optionString, w, h)

def select_random_manul( w, h ):
    aspect = w / float(h)
    n = 5
    r = Random( (w,h,11) )
    m = [ m for m in manuls.values() if m.width >= w and m.height >= h ]
    if not m:
        return None
    return r.choice( sorted( m, key = lambda manul: abs(manul.aspect - aspect) )[:n] )

def convert( srcimg, manul, w, h, optionString, dstname ):
    name = manul.filename
    srcw, srch = srcimg.size
    ratiow, ratioh = w/float(srcw), h/float(srch)
    roi = manul.region
    if ratiow != 1 and ratioh != 1:
        if ratioh > ratiow:
            desth = h
            destw = int( math.ceil( srcw * desth / float(srch)) )
        else:
            destw = w
            desth = int( math.ceil( srch * destw / float(srcw)) )
        srcimg = srcimg.resize( (destw,desth), Image.ANTIALIAS )
        if roi:
            (x0,y0), (x1,y1) = roi
            x0 *= destw / float(srcw )
            x1 *= destw / float(srcw )
            y0 *= desth / float(srch )
            y1 *= desth / float(srch )
            roi = (x0,y0), (x1,y1)
        srcw, srch = destw, desth
    assert (srcw == w) or (srch == h)
    assert (srcw >=  w) and (srch >= h)
    if srcw > w:
        if not roi:
            pad = int( (srcw - w) / 2 )
        else:
            (x0,y0), (x1,y1) = roi
            poix = (x0+x1)/2.0
            pad = min( srcw - w, max(0, int(poix - w/2)) )
        srcimg = srcimg.crop( (pad,0,pad+w-1,h-1) )
    elif srch > h:
        if not roi:
            pad = int( (srch - h) / 2 )
        else:
            (x0,y0), (x1,y1) = roi
            poiy = (y0+y1)/2.0
            pad = min( srch - h, max(0,int(poiy - h/2)) )
        srcimg = srcimg.crop( (0,pad,w-1,pad+h-1) )
    for option in optionString:
        if option == "g":
            srcimg = ImageOps.grayscale( srcimg )
        elif option == "n":
            srcimg = ImageOps.invert( srcimg )
        elif option == "s":
            sepia = 0xff, 0xf0, 0xc0
            srcimg = srcimg.convert( "L" )
            srcimg.putpalette( [ int( (i/3/255.0) * sepia[i%3] ) for i in range(256*3) ] )
            srcimg = srcimg.convert( "RGB" )
    # todo locking, write to temp and then copy
    srcimg.save( dstname )
    return True
    
class serve_image:        
    def GET(self, optionsConcatenated):
        wh = []
        specificId = None
        optionList = []
        for option in optionsConcatenated.split("/"):
            if not option:
                continue
            if option.isdigit():
                wh.append( int(option) )
            elif option.startswith("m"):
                specificId = int( option[1:] )
            else:
                optionList.append( option )
        if len( wh ) == 0:
            w = h = 640
        elif len( wh ) == 1:
            w = h =  wh[0]
        else:
            assert len( wh ) == 2
            w, h = wh
        optionString = "".join( map( map_option, optionList ) )
        try:
            if not specificId:
                manul = select_random_manul( w, h )
            else:
                manul = manuls[ specificId ]
        except:
            return "Oops! (no manul large enough)"
        fn = filename( manul.filename, w, h, optionString )
        if not os.path.exists( cachedDir + fn ):
            convert( Image.open( sourceDir + manul.filename ), manul, w, h, optionString, cachedDir + fn )
        try:
            with open( cachedDir + fn, "rb" ) as f:
                data = f.read()
                web.header( "Content-Type", "image/jpeg" )
                return data
        except:
            return "Oops!"

class serve_page:
    def GET(self, name, *args, **kwargs):
        kwargs = {}
        return {
            'index': render.index,
            'about': render.about
        }[ name ]( urlRoot, *args, **kwargs )

class index:
    def GET(self):
        return render.index( urlRoot )

if not testRun:
    app = web.application(urls, globals(), autoreload = False)
    application = app.wsgifunc()
else:
    app = web.application(urls, globals())

if __name__ == "__main__":
    app.run()

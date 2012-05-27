import web
import Image
import ImageOps
import os.path
import os
import math
import sys
import json
import datetime
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
    '/(index|about)(?:/|\.html?)?', 'serve_page',
    '/(gallery|attribution)(?:/|\.html?)?', 'serve_gallery',
    '/?', 'index',
    '/(.+)', 'serve_image',
)

class Manul:
    def __init__(self, number = None, filename = None, author = "", license = "", attribution_link = "", nominal_size = None, region = None, actual_size = None):
        assert number
        assert filename
        self.number = int(number)
        self.filename = filename
        self.author = author
        self.license = license
        self.attribution_link = attribution_link
        self.untransformed_region = self.region = region
        self.nominal_size = nominal_size
        if actual_size:
            self.actual_size = actual_size
        else:
            img = Image.open( sourceDir + filename )
            self.actual_size = img.size
        ax, ay = self.actual_size
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
    def encode(self):
        return {
            u"image": self.filename,
            u"author": self.author,
            u"attribution_link": self.attribution_link,
            u"license": self.license,
            u"size": self.nominal_size,
            u"region": self.untransformed_region,
            u"actual_size": self.actual_size
        }

def loadManul( key, j ):
    return Manul( number = int(key),
                  filename = j[u"image"],
                  author = j.get(u"author") or "",
                  attribution_link = j.get(u"attribution_link") or "",
                  license = j.get(u"license") or "",
                  nominal_size = j.get(u"size"),
                  region = j.get(u"region"),
                  actual_size = j.get(u"actual_size") )

def findfiles( jsonFile = None ):
    jsonFile = jsonFile or (sourceDir + "manuls.json")
    with open( jsonFile, "r" ) as f:
        rv = [ loadManul( key, record ) for key, record in json.load( f ).items() ]
    return dict( map( lambda r : (r.number, r), rv ) )

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

def select_random_manul( manuls, w, h ):
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
        try:
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
        except:
            raise web.internalerror( render.error( "error parsing arguments" ) )
        try:
            if not specificId:
                manul = select_random_manul( findfiles(), w, h )
            else:
                manul = findfiles()[ specificId ]
            fn = filename( manul.filename, w, h, optionString )
        except:
            if specificId:
                raise web.internalerror( render.error( "manul not found" ) )
            else:
                raise web.internalerror( render.error( "manul not found (requested resolution may be too high)" ) )
        try:
            if not os.path.exists( cachedDir + fn ):
                convert( Image.open( sourceDir + manul.filename ), manul, w, h, optionString, cachedDir + fn )
        except:
            raise web.internalerror( render.error( "error processing manul" ) )
        path = cachedDir + fn
        mtime = os.stat( path ).st_mtime
        if web.http.modified( date = datetime.datetime.fromtimestamp(mtime) ): 
            try:
                with open( path, "rb" ) as f:
                    data = f.read()
                    web.header( "Content-Type", "image/jpeg" )
                    return data
            except:
                raise web.internalerror( render.error( "error retrieving manul" ) )

def render_gallery_entry( keyvalue ):
    key, manul = keyvalue
    showWidth = 300
    showHeight = 300
    url = "%s/m%d/%d/%d" % (urlRoot, key, showWidth, showHeight )
    desc = "Picture of a manul by %s" % manul.author
    return unicode(render.gallery_entry( key, url, desc, manul.author, manul.license, manul.attribution_link, manul.width, manul.height ))

class serve_gallery:
    def GET(self, *args, **kwargs):
        return render.gallery( map( render_gallery_entry, findfiles().items() ) )

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

def notfound():
    return web.notfound( render.error( "page not found" ) )

def internalerror():
    return web.internalerror( render.error( "internal server error" ) )

if not testRun:
    app = web.application(urls, globals(), autoreload = False)
    application = app.wsgifunc()
else:
    app = web.application(urls, globals())

app.notfound = notfound
app.internalerror = internalerror

if __name__ == "__main__":
    app.run()

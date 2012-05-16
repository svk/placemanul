import web
import Image
import os.path
import os
import math
from random import Random

urlRoot = ""
sourceDir = "/var/www/placemanul/source/"
cachedDir = "/var/www/placemanul/static/"

render = web.template.render( "/var/www/placemanul/templates/" )

urls = (
    '/([^\/]+)/([0-9]+)/([0-9]+)/?', 'serve_image',
    '/([0-9]+)/([0-9]+)/?', 'serve_image',
    '/([^\/]+)/([0-9]+)/?', 'serve_image',
    '/([0-9]+)/?', 'serve_image',
    '/([a-z]+)/?', 'serve_page',
    '/?', 'index'
)

def findfiles():
    return os.listdir( sourceDir )

def scanfile( filename ):
    img = Image.open( sourceDir + filename )
    return filename, img.size

manuls = [ scanfile( m ) for m in findfiles() ]

def filename( name, w, h ):
    return "%s-%dx%d.jpeg" % (name, w, h)

def select_random_manul( w, h ):
    aspect = w / float(h)
    n = 5
    r = Random( (w,h,11) )
    m = [ (name,(w_, h_)) for (name, (w_,h_)) in manuls if w_ >= w and h_ >= h ]
    if not m:
        return None
    return r.choice( sorted( m, key = lambda (_,(w,h)): abs(w/float(h) - aspect) )[:n] )

def convert( srcimg, name, w, h, dstname ):
    srcw, srch = srcimg.size
    ratiow, ratioh = w/float(srcw), h/float(srch)
    if ratiow != 1 and ratioh != 1:
        if ratioh > ratiow:
            desth = h
            destw = int( math.ceil( srcw * desth / float(srch)) )
        else:
            destw = w
            desth = int( math.ceil( srch * destw / float(srcw)) )
        srcimg = srcimg.resize( (destw,desth), Image.ANTIALIAS )
        srcw, srch = destw, desth
    assert (srcw == w) or (srch == h)
    assert (srcw >=  w) and (srch >= h)
    if srcw > w:
        pad = int( (srcw - w) / 2 )
        srcimg = srcimg.crop( (pad,0,pad+w-1,h-1) )
    elif srch > h:
        pad = int( (srch - h) / 2 )
        srcimg = srcimg.crop( (0,pad,w-1,pad+h-1) )
    # todo locking, write to temp and then copy
    srcimg.save( dstname )
    return True
    
class serve_image:        
    def GET(self, options = None, w = None, h = None):
        if h == None and (not type(options) == str):
            w, h = options, w
        w = int( w or 640 )
        h = int( h or w )
        try:
            srcname, _ = select_random_manul( w, h )
        except:
            return "Oops! (no manul large enough)"
        fn = filename( srcname, w, h )
        if not os.path.exists( cachedDir + fn ):
            convert( Image.open( sourceDir + srcname ), srcname, w, h, cachedDir + fn )
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

app = web.application(urls, globals(), autoreload = False)
application = app.wsgifunc()

if __name__ == "__main__":
    app.run()

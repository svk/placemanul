import placemanul
import sys
import json

if __name__=='__main__':
    placemanul.sourceDir, inputJson, outputJson = sys.argv[1:]
    with open( outputJson, "w" ) as f:
        json.dump( dict( [ (key, value.encode()) for (key,value) in placemanul.findfiles( inputJson ).items() ] ), f , indent = 1)
    

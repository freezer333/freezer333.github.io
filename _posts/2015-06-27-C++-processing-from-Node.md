---
layout: post
title:  "C++ Processing from Node.js"
date:   2015-06-27 14:16:27
categories: integration C++ Node.js
---
# Chapter 2 - Calling C++ from Node.js
I love doing high-level work in node.js, but sometimes I'm working on data analysis that needs to be done in a higher performance language.  C++ is usually a good choice for these tasks, and a great thing about node is how easy it is to move data to and from C++ with the node's addon mechanism - using the V8 API.  There's a lot of documentation on the [node](http://nodejs.org/api/addons.html) site, but I've found it hard to locate full examples where there are full data structures flowing between JavaScript and C++... so I wrote this.

In this post I'll show you how to call C++ from JavaScript, passing JavaScript objects to C++ - which are turned into first-class objects matching a C++ class definition.  I'll show you how to pass different C++ objects back to node as JavaScript objects.  I'll also show you how to pass lists of objects back and forth, along with nested class/object use-cases. **Its a big topic, I've broken it into four posts**.

Once you've looked at this series, there's still a lot more to learn about using C++ within Node.js - topics like wrapping existing C++ objects, working with multiple versions of the V8 API, and deployment on different platforms.  If you are looking for a manual that goes over all this and more, check out my [ebook on this topic](http://scottfrees.com/ebooks/nodecpp/) - it's a great shortcut!

# Integration Pattern
I've chosen to handle objects in a way that minimizes the impact of the actual C++ code called by node.  This means that I did *not* employ the V8 class wrapping strategies, instead electing to code all transfer between V8 data types and C++ classes myself, in separate functions.  I like this method, because it keeps the V8 code isolated - and works when you don't want to directly mess with existing C++ code you are calling from node.  If you are looking to have a more automatic method of mapping V8 to C++ data structures, see this [excellent article](http://code.tutsplus.com/tutorials/writing-nodejs-addons--cms-21771), along with the [Node.js documentation](http://nodejs.org/api/addons.html#addons_wrapping_c_objects).

# Node Version
The code presented is based on Node.js v0.12 and above.  Node v0.12 integrated a new version of the V8 JavaScript engine, which contained a lot of API breaking changes to C++ integration.  Read more about it [here](https://strongloop.com/strongblog/node-js-v0-12-c-apis-breaking/).  **If you aren't using Node v0.12 and above, some of this code won't work for you!**

# Background - Data Schema
I'm going to create a node program sends a json object containing rain fall sample data to C++ for processing.  The sample data contains a list of `locations`, marked by their latitude and longitude.  Each `location` also has a list of `samples` containing the date when the measurement was taken and the amount of rainfall in cm.  Below is an example.

*Note - you can find all the source code for this post [on github, here](https://github.com/freezer333/nodecpp-demo)*.

```json
{
  "locations" : [
    {
      "latitude" : "40.71",
      "longitude" : "-74.01",
      "samples" : [
          {
             "date" : "2014-06-07",
             "rainfall" : "2"
          },
          {
             "date" : "2014-08-12",
             "rainfall" : "0.5"
          },
          {
             "date" : "2014-09-29",
             "rainfall" : "1.25"
          }
       ]
    },
    {
      "latitude" : "42.35",
      "longitude" : "-71.06",
      "samples" : [
          {
             "date" : "2014-03-03",
             "rainfall" : "1.75"
          },
          {
             "date" : "2014-05-16",
             "rainfall" : "0.25"
          },
          {
             "date" : "2014-03-18",
             "rainfall" : "2.25"
          }
       ]
    }
  ]
}
```
The JavaScript code will call a C++ addon to calculate average and median rainfall for each location.  *Yes, I know average/median is not exactly a "heavy compute" task - this is just for show*.  In Part 1 of this tutorial, I'll just pass one location to C++ (with several rainfall samples) and C++ will just return the average as a simple numeric value.

# Creating the C++ addon
We'll create the logic / library by defining simple C++ classes to represent locations and samples, and a function to calculate the average rainfall for a given location.

```c++
class sample {
public:
  sample (); // in rainfall.cc
  sample (string d, double r) ; // in rainfall.cc
  string date;
  double rainfall;
};

class location {
public:
  double longitude;
  double latitude;
  vector<sample> samples;
};

// Will return the average (arithmetic mean) rainfall for the give location
double avg_rainfall(location & loc); // code in rainfall.cc
```
If you download the [source from github](https://github.com/freezer333/nodecpp-demo) you can see the implementation along with a simple test program.  Everything related to the C++ code and building the addon is in a directory called `/cpp`.

Now we need to make this code available to Node.js by building it as an addon.

## Creating the V8 entry point code
To expose our C++ "library" as a node.js addon we build some wrapper code.  The [Node.js official documentation](http://nodejs.org/api/addons.html) has some very good explanation of the basics to this.

We need to create a new .cc file (I called it `rainfall_node.cc`), which includes
the `node.h` and `v8.h` headers.  Next, we need to define an entry point for our addon - which is achieved by creating a function and registering it via a macro provided by the node/v8 headers.

```cc
#include <node.h>
#include <v8.h>
#include "rainfall.h"

using namespace v8;

void init(Handle <Object> exports, Handle<Object> module) {
 // we'll register our functions to make them callable from node here..
}

// associates the module name with initialization logic
NODE_MODULE(rainfall, init)
```
In the `init` function (we can name it anything, as long as we associate it in the NODE_MODULE macro) we will define which functions are going to be exposed to Node.js when are module is included/required.  As you will see, the wrapper code to do all this gets a little ugly, which is why I think its important to keep your clean C++ code (the rainfall.h/cc files) separate from all this.

So the first thing I'll do is expose the `avg_rainfall` method from rainfall.h by creating a new function in `rainfall_node.cc`.

```cpp
void AvgRainfall(const v8::FunctionCallbackInfo<v8::Value>& args) {
  Isolate* isolate = args.GetIsolate();

  Local<Number> retval = v8::Number::New(isolate, 0);
  args.GetReturnValue().Set(retval)
}
```
The signature of this function is dictated by the node/v8 API - and its the first place we are seeing some [important changes](https://strongloop.com/strongblog/node-js-v0-12-c-apis-breaking/) that arrived in Node v 0.12.  The input arguments which will be passed from a JavaScript call are V8 objects.   The `isolate` object represents the actual V8 VM instance (your heap) - it will be passed around quite a bit, as its required when creating new instances of objects and primitives.

The return value is set at the last line of the function (note, its a `void` function in Node v0.12+).  As currently written, the function always just returns 0 as the average rainfall - we'll fix that soon...

Now lets make this function callable from node, by registering it within the `init` function from earlier.

```cpp
void init(Handle <Object> exports, Handle<Object> module) {
  NODE_SET_METHOD(exports, "avg_rainfall", AvgRainfall);
}
```
The init function is called when the module is first loaded in a node application; it is given an export and module object representing the module being constructed and the object that is returned after the `require` call in JavaScript.  The `NODE_SET_METHOD` call is adding a method called `avg_rainfall` to the exports, associated with our actual `AvgRainfall` function from above.  From JavaScript, we'll see a function called "avg_rainfall", which at this point just returns 0.

Much of what I've covered so far can be found in the standard Node tutorials.  Now its time to modify the `AvgRainfall` wrapper code so it can accept JavaScript objects (`location`) and transform them into the C++ versions in order to actually call the **actual** average rainfall function we defined originally in `rainfall.cc`.

### Mapping JavaScript object to C++ class
The `const v8::FunctionCallbackInfo<v8::Value>& args` input parameter represents a collection of all arguments passed by JavaScript when the `AvgRainfall` function is called.  I'll explain how this is setup later - but for example, you might have the following JavaScript code:

```js
var rainfall = require("rainfall");
var location = {
  latitude : 40.71, longitude : -74.01,
       samples : [
          { date : "2014-06-07", rainfall : 2 },
          { date : "2014-08-12", rainfall : 0.5}
       ] };

console.log("Average rain fall = " + rainfall.avg_rainfall(location) + "cm");
```
To do this, we need some additional code to extract the object properties and instantiate C++ objects.  I'll pack this transfer code into a separate function called within the newly revised `AvgRainfall` function:

```cpp
void AvgRainfall(const v8::FunctionCallbackInfo<v8::Value>& args) {
  Isolate* isolate = args.GetIsolate();

  location loc = unpack_location(isolate, args);
  double avg = avg_rainfall(loc);

  Local<Number> retval = v8::Number::New(isolate, avg);
  args.GetReturnValue().Set(retval);
}
```
The `unpack_location` function accepts the VM instance and the argument list, and unpacks the V8 object into a new `location` object - and returns it.

```cpp
location unpack_location(Isolate * isolate, const v8::FunctionCallbackInfo<v8::Value>& args) {
  location loc;
  Handle<Object> location_obj = Handle<Object>::Cast(args[0]);
  Handle<Value> lat_Value =
                location_obj->Get(String::NewFromUtf8(isolate,"latitude"));
  Handle<Value> lon_Value =
                location_obj->Get(String::NewFromUtf8(isolate,"longitude"));
  loc.latitude = lat_Value->NumberValue();
  loc.longitude = lon_Value->NumberValue();

  Handle<Array> array =  Handle<Array>::Cast(
                        location_obj->Get(
                              String::NewFromUtf8(isolate,"samples")));

  int sample_count = array->Length();
  for ( int i = 0; i < sample_count; i++ ) {
    sample s = unpack_sample(isolate, Handle<Object>::Cast(array->Get(i)));
    loc.samples.push_back(s);
  }
  return loc;
}
```
The `unpack_sample` function is similar - this is all a matter of unpacking the data from V8's data types.

```cpp
sample unpack_sample(Isolate * isolate, const Handle<Object> sample_obj) {
  sample s;
  Handle<Value> date_Value =
               sample_obj->Get(String::NewFromUtf8(isolate, "date"));
  Handle<Value> rainfall_Value =
              sample_obj->Get(String::NewFromUtf8(isolate, "rainfall"));

  v8::String::Utf8Value utfValue(date_Value);
  s.date = std::string(*utfValue);

  // Unpack the numeric rainfall amount directly from V8 value
  s.rainfall = rainfall_Value->NumberValue();
  return s;
}
```

## Installing node-gyp
To create a C++ addon we'll need to compile/package the .cc/.h files using `node-gyp`.  As discussed [here](http://www.benfarrell.com/2013/01/03/c-and-node-js-an-unholy-combination-but-oh-so-right/), you don't want to be using the deprecated WAF tools for this step.

You can find a lot more detail about `node-gyp` on [the project's site](https://github.com/TooTallNate/node-gyp).

>node-gyp is a cross-platform command-line tool written in Node.js for compiling native addon modules for Node.js. It bundles the gyp project used by the Chromium team and takes away the pain of dealing with the various differences in build platforms.

Installing it is easy - but before executing the following make sure you have the following already installed on your machine:

* python (v2.7 recommended, v3.x.x is not supported)
* make (or Visual Studio on Windows)
* C/C++ compiler toolchain, like GCC (or Visual Studio on Windows)

If you meet those requirements, go ahead and install `node-gyp` globally on your system.

```console256
> npm install -g node-gyp
```
## Building the C++ addon
Next we need to create a build file that instructs `node-gyp` on how to assemble our addon.  Create a file called `binding.gyp` in the same directory as the C++ code you have already.

```js
{
  "targets": [
    {
      "target_name": "rainfall",
      "sources": [ "rainfall.cc" , "rainfall_node.cc" ],
      "cflags": ["-Wall", "-std=c++11"],
      'xcode_settings': {
        'OTHER_CFLAGS': [
          '-std=c++11'
        ],
      },
    }
  ]
}
```
This is just a json file with a collection of properties.  The target name is your addon/module name - **it must match the name you gave in NODE_MODULE macro in the `rainfall_node.cc` file!**.  The sources property should list all C++ code files (you do not need to list the headers) that will be compiled.  I've also added compiler flags, particularly because I'm using some C++ 11 code in rainfall.cc. I needed to add the xcode_settings property to make this work on OS X (see background [here](https://github.com/TooTallNate/node-gyp/issues/26)).

With this is place, you can build your module:

```
> node-gyp configure build
```
If all goes well here you will have a `/build/Release` folder created right alongside your C++ code files.  Within that folder, there should be a `rainfall.node` output file.  **This is your addon**... ready to be required from node.

# Node.js app
Below is the same JavaScript listing from above, with the only change being the require call - which is a little ugly because we are requiring a local package (I'll explain how to package this for npm usage in another post).  Create this file (rainfall.js) in the directory **above** the cpp folder containing your C++ source code.

```js
var rainfall = require("./cpp/build/Release/rainfall.node");
var location = {
    latitude : 40.71, longitude : -74.01,
       samples : [
          { date : "2014-06-07", rainfall : 2 },
          { date : "2014-08-12", rainfall : 0.5}
       ] };

console.log("Average rain fall = " + rainfall.avg_rainfall(location) + "cm");
```
You should be able to run it - and see that your C++ module has been called!

```
> node rainfall.js
Average rain fall = 1.25cm
```

# Next up...
We now have a fully functional node app calling C++.  We've successfully transformed a single JavaScript object into a C++ object.  In [Part 2](http://blog.scottfrees.com/c-processing-from-node-js-part-2) of this series, I'll expand on this example so the C++ code returns a full "result" object - along the lines of the class defined below.

```c++
class rain_result {
   public:
       float median;
       float mean;
       float standard_deviation;
       int n;
};
```

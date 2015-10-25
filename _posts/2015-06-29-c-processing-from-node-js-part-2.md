# Chapter 3:  Returning Objects from C++

This article is Part 2 of a series of posts on moving data back and forth between Node.js and C++.  In [Part 1](http://blog.scottfrees.com/c-processing-from-node-js), I built up an example of processing rainfall accumulation data in C++ and returning a simple statistic (average) back to JavaScript.

The JavaScript object passed into C++ looked something like this:

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

And we called C++ by invoking a function exposed using the V8 API.

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

In Part 1, we focused only on unpacking/transforming a JavaScript input object into a regular old C++ object.  We returned a primitive (average, as a `double`) - which was pretty easy.  I also wrote a lot about how to get your addon built using `node-gyp` - which I won't repeat here.  *Remember, this code is targeting the V8 C++ API distributed with Node v0.12 and above*

*Note - you can find all the source code for this post [on github, here](https://github.com/freezer333/nodecpp-demo)*.

In this post - Part 2 - I'm going to now return an object back to JavaScript consisting of several statistics about the list of rainfall samples passed into C++.  The result object will look like this in C++:

```c++
// declared in rainfall.h
class rain_result {
   public:
       float median;
       float mean;
       float standard_deviation;
       int n;
};
```

As explained in [Part 1](), I'm keeping the "business" part of my C++ code completely separate from the code dealing with V8 integration.  So the class above has been added to the `rainfall.h / rainfall.cc` files.

# Handling the input
We're going to now create a new callable function for the Node addon.  So, in the rainfall_node.cc file (where we put all our V8 integration logic), I'll add a new function and register it with the module's exports.

```c++
void RainfallData(const v8::FunctionCallbackInfo<v8::Value>& args) {
  Isolate* isolate = args.GetIsolate();

  location loc = unpack_location(isolate, args);
  rain_result result = calc_rain_stats(loc);

/*
 .... return the result object back to JavaScript  ....
*/
}
```
Recall from [Part 1](), the `unpack_location` function is where I'm extracting the location (and rainfall samples) from the JavaScript arguments.  I've introduced a new function in `rainfall.h / rainfall.cc` called `calc_rain_stats` which returns a `rain_result` instance based on the `location` instance it is given.  It computes mean/median/standard deviation (see [here](https://github.com/freezer333/nodecpp-demo/blob/master/cpp/rainfall.cc) for implementation.

The `RainfallData` function is exported with the addon by adding another call to `NODE_SET_METHOD` inside the `init` function in `rainfall_node.cc`.

```c++
void init(Handle <Object> exports, Handle<Object> module) {
  // from part 1
  NODE_SET_METHOD(exports, "avg_rainfall", AvgRainfall);
  // now added for part 2
  NODE_SET_METHOD(exports, "data_rainfall", RainfallData);
}
```

# Building the JavaScript object and returning it
After unpacking the `location` object inside the RainfallData function, we got a `rainfall_result` object:

```C++
rain_result result = calc_rain_stats(loc);
```

Now its time to return that - and to do so we'll create a new V8 object, transfer the rain_result data into it, and return it back to JavaScript.

```C++
void RainfallData(const v8::FunctionCallbackInfo<v8::Value>& args) {
  Isolate* isolate = args.GetIsolate();

  location loc = unpack_location(isolate, args);
  rain_result result = calc_rain_stats(loc);

  // Creates a new Object on the V8 heap
  Local<Object> obj = Object::New(isolate);

  // Transfers the data from result, to obj (see below)
  obj->Set(String::NewFromUtf8(isolate, "mean"),
                            Number::New(isolate, result.mean));
  obj->Set(String::NewFromUtf8(isolate, "median"),
                            Number::New(isolate, result.median));
  obj->Set(String::NewFromUtf8(isolate, "standard_deviation"),
                            Number::New(isolate, result.standard_deviation));
  obj->Set(String::NewFromUtf8(isolate, "n"),
                            Integer::New(isolate, result.n));

  // Return the object
  args.GetReturnValue().Set(obj);
}
```

First notice the similarities between this function and the AvgRainfall Function from Part 1. They both follow the similar pattern of creating a new variable on the V8 heap and returning it by setting the return value associated with the `args` variable passed into the function.  The difference now is that actually setting the value of the variable being returned is more complicated.  In AvgRainfall, we just created a new `Number`:

```C++
Local<Number> retval = v8::Number::New(isolate, avg);
```

Now, we have we instead move the data over one property at time:

```C++
Local<Object> obj = Object::New(isolate);
obj->Set(String::NewFromUtf8(isolate, "mean"),
                   Number::New(isolate, result.mean));
obj->Set(String::NewFromUtf8(isolate, "median"),
                   Number::New(isolate, result.median));
obj->Set(String::NewFromUtf8(isolate, "standard_deviation"),
                   Number::New(isolate, result.standard_deviation));
obj->Set(String::NewFromUtf8(isolate, "n"),
                   Integer::New(isolate, result.n));
```

While its a bit more code - the object is just being built up with a series of named properties - its pretty straightforward.  

# Invoking a from JavaScript
Now that we've completed the C++ side, we need to rebuild our addon:

```
> node-gyp configure build
```

In JavaScript, we can now call both methods, and we'll see the object returned by our new data_rainfall method returns a real JavaScript object.

```JavaScript
//rainfall.js
var rainfall = require("./cpp/build/Release/rainfall");
var location = {
    latitude : 40.71, longitude : -74.01,
       samples : [
          { date : "2015-06-07", rainfall : 2.1 },
          { date : "2015-06-14", rainfall : 0.5},
          { date : "2015-06-21", rainfall : 1.5},
          { date : "2015-06-28", rainfall : 1.3},
          { date : "2015-07-05", rainfall : 0.9}
       ] };

var avg = rainfall.avg_rainfall(location)
console.log("Average rain fall = " + avg + "cm");

var data = rainfall.data_rainfall(location);

console.log("Mean = " + data.mean)
console.log("Median = " + data.median);
console.log("Standard Deviation = " + data.standard_deviation);
console.log("N = " + data.n);
```

```console256
> node rainfall.js
Average rain fall = 1.26cm
Mean = 1.2599999904632568
Median = 1.2999999523162842
Standard Deviation = 0.6066300272941589
N = 5
```

# Next up...
You now have seen examples of passing simple objects back and forth between C++ and Node.js.  In the [next part](http://blog.scottfrees.com/c-processing-from-node-js-part-3-arrays) of the series, I'll look at some more complex use cases, where lists of objects and nested objects are being moved between JavaScript and the addon.

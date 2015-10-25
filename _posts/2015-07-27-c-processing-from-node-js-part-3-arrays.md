# Chapter 4:  Working with Arrays of data

This article is Part 3 of a series of posts on moving data back and forth between Node.js and C++. In [Part 1](http://blog.scottfrees.com/c-processing-from-node-js), I built up an example of processing rainfall accumulation data in C++ and returning a simple statistic (average) back to JavaScript. In [Part 2](http://blog.scottfrees.com/c-processing-from-node-js-part-2) I modified the C++ addon to return a JavaScript object representing more complete statistics about each location/sample.

In each of the previous posts, the JavaScript objects being passed into C++ looked like this:

```js
{
      "latitude" : "42.35",
      "longitude" : "-71.06",
      "samples" : [
          { date : "2015-06-07", rainfall : 2.1 },
          { date : "2015-06-14", rainfall : 0.5},
          { date : "2015-06-21", rainfall : 1.5},
          { date : "2015-06-28", rainfall : 1.3},
          { date : "2015-07-05", rainfall : 0.9}
       ]
    }
```

In Part 2, the C++ addon returned a `rain_result` object that looked list this:

```js
{
	median: 1.2999999523162842
	mean:1.2599999904632568
	standard_deviation: 0.6066300272941589
	n:5
}
```

Now we'll look at passing an array of location data into C++ and having C++ return an array of results back to us.  All the code for this series of posts is found [here](https://github.com/freezer333/nodecpp-demo).

# Receiving an Array from Node
If you haven't read [Parts 1](http://blog.scottfrees.com/c-processing-from-node-js) and [2](http://blog.scottfrees.com/c-processing-from-node-js-part-2) of this post please do so now - its important you understand how I'm integrating C++ and JavaScript classes.  Instead of using the V8 object wrapping API, I'm just packing/unpacking data from V8's native objects into and out of my [POCOs](https://en.wikipedia.org/wiki/Plain_Old_C%2B%2B_Object).  While there is a little added work upfront, we'll see this work now be leveraged to make list processing really very easy.  

## Registering the callable addon function
As always, we start by writing a C++ function in `/cpp/rainfall_node.cc` that will be callable from Node.js.

```cpp
void CalculateResults(const v8::FunctionCallbackInfo<v8::Value>&args) {
    Isolate* isolate = args.GetIsolate();
    std::vector<location> locations;  // we'll get this from Node.js
    std::vector<rain_result> results; // we'll build this in C++

    // we'll populate this with the results
    Local<Array> result_list = Array::New(isolate);

    // ... and send it back to Node.js as the return value
    args.GetReturnValue().Set(result_list);
}
....
void init(Handle <Object> exports, Handle<Object> module) {
  // part 1
  NODE_SET_METHOD(exports, "avg_rainfall", AvgRainfall);
  // part 2
  NODE_SET_METHOD(exports, "data_rainfall", RainfallData);
  // part 3
  NODE_SET_METHOD(exports, "calculate_results", CalculateResults);
}
```
The `CalculateResults` function will extract a list of location objects from the parameters (`args`) and eventually return a fully populated array of results.  We make it callable by calling the `NODE_SET_METHOD` in the `init` function - so we can call `calculate_results` in JavaScript.

Before we implement the C++, lets look at how this will all be called in JavaScript.  First step is to rebuild the addon from the `cpp` directory:

```
>  node-gyp configure build
```
In the rainfall.js, we'll construct an array of locations and invoke our addon:

```js
// Require the Addon
var rainfall = require("./cpp/build/Release/rainfall");

var makeup = function(max) {
    return Math.round(max * Math.random() * 100)/100;
}

// Build some dummy locations
var locations = []
for (var i = 0; i < 10; i++ ) {
    var loc = {
        latitude: makeup(180),
        longitude: makeup(180),
        samples : [
            {date: "2015-07-20", rainfall: makeup(3)},
            {date: "2015-07-21", rainfall: makeup(3)},
            {date: "2015-07-22", rainfall: makeup(3)},
            {date: "2015-07-23", rainfall: makeup(3)}
        ]
    }
    locations.push(loc);
}

// Invoke the Addon
var results = rainfall.calculate_results(locations);

// Report the results from C++
var i = 0;
results.forEach(function(result){
    console.log("Result for Location " + i);
    console.log("--------------------------");
    console.log("\tLatitude:         " + locations[i].latitude.toFixed(2));
    console.log("\tLongitude:        " + locations[i].longitude.toFixed(2));
    console.log("\tMean Rainfall:    " + result.mean.toFixed(2) + "cm");
    console.log("\tMedian Rainfall:  " + result.median.toFixed(2) + "cm");
    console.log("\tStandard Dev.:    " + result.standard_deviation.toFixed(2) + "cm");
    console.log("\tNumber Samples:   " + result.n);
    console.log();
    i++;
})
```

When you run this with `node rainfall` you'll get no output, only because the C++ function is returning an empty array at this point.  Try putting a `console.log(results)` in, you should see `[]` print out.

## Extracting the Array in C++
Now lets skip back to our `CalculateResults` C++ function.  We've been given the function callback arguments object, and our first step is to cast it to a V8 array.

```cpp
void CalculateResults(const v8::FunctionCallbackInfo<v8::Value>&args) {
    Isolate* isolate = args.GetIsolate();
    ... (see above)...
    Local<Array> input = Local<Array>::Cast(args[0]);
    unsigned int num_locations = input->Length();
```

With the V8 array `input`, we'll now loop through and actually create a POCO `location` object using the `unpack_location` function we saw in [Part 2](http://blog.scottfrees.com/c-processing-from-node-js-part-2).  The return value from `unpack_location` is pushed onto a standard C++ vector.

```cpp
for (unsigned int i = 0; i < num_locations; i++) {
  locations.push_back(
       unpack_location(isolate, Local<Object>::Cast(input->Get(i)))
  );
}
```

Of course, now that we have a standard vector of `location` objects, we can call our existing `calc_rain_stats` function on each one and build up a vector of `rain_result` objects.

```cpp
results.resize(locations.size());
std::transform(
     locations.begin(),
     locations.end(),
     results.begin(),
     calc_rain_stats);
```

# Building an Array to return back from C++
Our next step is to move the data we've created into the V8 objects that we'll return.  First, we create a new V8 Array:

```cpp
Local<Array> result_list = Array::New(isolate);
```
We can now iterate through our `rain_result` vector and use the `pack_rain_result` function from [Part 2](http://blog.scottfrees.com/c-processing-from-node-js-part-2) to create a new V8 object and add it to the `result_list` array.

```cpp
for (unsigned int i = 0; i < results.size(); i++ ) {
      Local<Object> result = Object::New(isolate);
      pack_rain_result(isolate, result, results[i]);
      result_list->Set(i, result);
    }
```

And... we're all set.  Here's the complete code for the `CalculateResult` function:

```cpp
void CalculateResults(const v8::FunctionCallbackInfo<v8::Value>&args) {
    Isolate* isolate = args.GetIsolate();
    std::vector<location> locations;
    std::vector<rain_result> results;

    // extract each location (its a list)
    Local<Array> input = Local<Array>::Cast(args[0]);
    unsigned int num_locations = input->Length();
    for (unsigned int i = 0; i < num_locations; i++) {
      locations.push_back(
             unpack_location(isolate, Local<Object>::Cast(input->Get(i))));
    }

    // Build vector of rain_results
    results.resize(locations.size());
    std::transform(
          locations.begin(),
          locations.end(),
          results.begin(),
          calc_rain_stats);


    // Convert the rain_results into Objects for return
    Local<Array> result_list = Array::New(isolate);
    for (unsigned int i = 0; i < results.size(); i++ ) {
      Local<Object> result = Object::New(isolate);
      pack_rain_result(isolate, result, results[i]);
      result_list->Set(i, result);
    }

    // Return the list
    args.GetReturnValue().Set(result_list);
}
```

Do another `node-gyp configure build` and re-run ` node rainfall.js` and you'll see the fully populated output results from C++.

```
Result for Location 0
--------------------------
	Latitude:         145.45
	Longitude:        7.46
	Mean Rainfall:    1.59cm
	Median Rainfall:  1.65cm
	Standard Dev.:    0.64cm
	Number Samples:   4

Result for Location 1
--------------------------
	Latitude:         25.32
	Longitude:        98.64
	Mean Rainfall:    1.17cm
	Median Rainfall:  1.24cm
	Standard Dev.:    0.62cm
	Number Samples:   4
....

```

## About efficiency
You might be wondering, aren't we wasting a lot of memory by creating POCO copies of all the V8 data?  Its a good point, for all the data being passed into the C++ Addon, the V8 objects (which take up memory) are being moved into new C++ objects.  Those C++ (and their derivatives) are then copied into new V8 objects to be returned... we're doubling memory consumption and its also costing us processing time to do all this!

For most use cases I end up working with, the overhead of memory copying (both time and space) is dwarfed by the actual execution time of the algorithm and processing that I'm doing in C++.  If I'm going through the trouble of calling C++ from Node, its because the actual compute task is *significant*!  

For situations where the cost of copying input/output isn't dwarfed by your actual processing time, it would probably make more sense to use V8 object wrapping API instead.

# Next up... asynchronous execution
Now that we've seen how to move primitives, objects, and lists between Node and C++, in [Part 4](http://blog.scottfrees.com/c-processing-from-node-js-part-4-asynchronous-addons) we'll look at how to execute the bulk of our C++ work asynchronously in a separate thread using [libuv](http://libuv.org/) so JavaScript can just give the add-on a callback and continue on its way.

---
layout: post
title:  "C++ processing from Node.js - Part 4 - Asynchronous addons"
date:   2015-08-07 14:16:27
categories: integration C++ Node.js
---


# C++ processing from Node.js - Part 4 - Asynchronous addons

This article is Part 4 of a series of posts on moving data back and forth between Node.js and C++. In [Part 1](http://blog.scottfrees.com/c-processing-from-node-js), I built up an example of processing rainfall accumulation data in C++ and returning a simple statistic (average) back to JavaScript. In Parts [2](http://blog.scottfrees.com/c-processing-from-node-js-part-2) and [3](http://blog.scottfrees.com/c-processing-from-node-js-part-3-arrays), I covered more complex use cases involving moving lists and objects.  This post covers **asynchronous** C++ addons - which are probably the most useful.

# Why Asynchronous?
If you are dropping into C++ to do some calculations, chances are good that you are doing it for speed.  If you are going though all this trouble for speed, then you probably have a hefty calculation to do - and its going to take time (even in C++!).

Unfortunately, if you make a call from JavaScript to a C++ addon that executes synchronously, your JavaScript application will be **blocked** - waiting for the C++ addon to return control.  This basically goes against *ALL best-practices*, your event loop is stalled!

# Asynchronous addon API
If you haven't read parts 1-3 of this series, make sure you do - so you understand the data structures being passed back and forth.  We're sending in lists of lat/longitude positions with rainfall sample data, and C++ is returning back statistics on that data.  Its a contrived example, but its working so far.

So the idea is to change our API from this:

```js
// require the C++ addon
var rainfall = require("./cpp/build/Release/rainfall");
...
// call into the addon, blocking until it returns
var results = rainfall.calculate_results(locations);
print_rain_results(results);
```

.. to something like this:

```js
// pass a callback into the addon, and have the addon return immediately
rainfall.calculate_results_async(locations, function(results) {
  print_rain_results(results);
});
// we can continue here, before the callback is invoked.
```

... or just ...

```js
rainfall.calculate_results_async(locations, print_rain_results);
// we can continue here, before the callback is invoked.
```

# The C++ addon code
Our first step is to create yet another C++ function, and register it with our module.  This is basically the same as in the previous posts.  Make sure you take a look at the full code [here](https://github.com/freezer333/nodecpp-demo)

```cpp
// in node_rainfall.cc
void CalculateResultsAsync(const v8::FunctionCallbackInfo<v8::Value>&args) {
    Isolate* isolate = args.GetIsolate();

     // we'll start a worker thread to do the job
     // and call the callback here...

    args.GetReturnValue().Set(Undefined(isolate));
}
...
void init(Handle <Object> exports, Handle<Object> module) {
  ...
   NODE_SET_METHOD(exports, "calculate_results_async", CalculateResultsAsync);
}
```

The `CalculateResultsAsync` function is where we'll end up kicking off a worker thread using libuv  - but notice what it does right away:  it *returns*!  Nothing we fill into this function will be long running, all the real work will be done in the worker thread.

## Worker thread model
Lets do a quick overview of how worker threads should work in V8.  In our model, there are **two threads**.  

The first thread is the *event loop thread* - its the thread that our JavaScript code is executing in, and its the thread that we are **still in** when we cross over into C++ through the `calculate_results_async` function call.  This is the thread that we *don't* want to stall by doing heavy calculations!

The second thread (to be created) will be a worker thread managed by libuv, the library that supports asynchronous I/O in Node.  

Hopefully you're pretty familiar with threads - the key point here is that each thread has it's own stack - you can't share stack variables between the event loop thread and the worker thread!  Threads do share the same heap though - so that's where we are going to put our input and output data, along with state information.

On the C++ side of things, we're going to utilize **three functions** and a **struct** to coordinate everything:

1.  `Worker Data` (struct) - will store plain old C++ input (locations) and output (rain_results) and the callback function that can be invoked when work is complete
1.  `CalculateResultsAsync` - executes in event-loop thread, extracts input and stores it on the heap in *worker data*.
1.  `WorkAsync` - the function that the worker thread will execute.  We'll launch this thread from `CalculateResultsAsync` using the libuv API
1.  `WorkAsyncComplete` - the function that libuv will invoke when the worker thread is finished.  This function is executed on the *event loop thread*, **not** the worker thread.

I like pictures:
![Node and Libuv Worker Thread](http://scottfrees.com/node-worker-c.png)
<img src="https://docs.google.com/drawings/d/1DD6FajO_vGmOHpk1kM2KTvApSIjc7JFF7HlwBBwX8jw/pub?w=960&h=720">

Lets look at the C++ code, starting with our Work Data structure:

```cpp
struct Work {
  uv_work_t  request;
  Persistent<Function> callback;

  std::vector<location> * locations;
  std::vector<rain_result> * results;
};
```

The vector pointers are going to store our input and output, which will be allocated on the heap.  The request object is a handle that will actually loop back to the work object - the libuv API accepts pointers of type `uv_work_t` when starting worker threads. The `callback` variable is going to store the JavaScript callback.  Importantly, its `Persistent<>`, meaning it will be stored on the heap so we can call it when the worker is complete.  This seems confusing (at least to me), since the callback will be executed in the event-loop thread, but the reason we need to put into the heap is because when we initially return to JavaScript, all V8 locals are destroyed.  A new Local context is created when we are about to call the JavaScript callback after the worker thread completes.


Now lets look at the `CalculateResultsAsync` function

```cpp
void CalculateResultsAsync(const v8::FunctionCallbackInfo<v8::Value>&args) {
    Isolate* isolate = args.GetIsolate();

    Work * work = new Work();
    work->request.data = work;
```

Notice that the Work struct is created on the heap.  Remember, local variables (and V8 Local objects) will be destroyed when this function returns - even though our worker thread will still be active.  Here we also set the `uv_work_t` data pointer to point right back to the `work` struct so libuv will pass it back to us on the other side.

```cpp
    ...
    // extract each location (its a list) and store it in the work package
    // locations is on the heap, accessible in the libuv threads
    work->locations = new std::vector<location>();
    Local<Array> input = Local<Array>::Cast(args[0]);
    unsigned int num_locations = input->Length();
    for (unsigned int i = 0; i < num_locations; i++) {
      work->locations->push_back(
          unpack_location(isolate, Local<Object>::Cast(input->Get(i)))
      );
    }
```

The code above is really the same as from [Part 3](http://blog.scottfrees.com/c-processing-from-node-js-part-3-arrays). The key part is that we are extracting the arguments sent from JavaScript and putting them in a locations vector stored on the heap, within the `work` struct.

Where earlier we now just went ahead and processed the rainfall data, now we'll kick off a worker thread using libuv.  First we store the callback sent to use from JavaScript, and then we're off.  Notice as soon as we call `uv_queue_work`, we return - the worker is executing in its own thread (`uv_queue_work` returns immediately).  

```cpp

    // store the callback from JS in the work package so we can
    // invoke it later
    Local<Function> callback = Local<Function>::Cast(args[1]);
    work->callback.Reset(isolate, callback);

    // kick of the worker thread
    uv_queue_work(uv_default_loop(),&work->request,
        WorkAsync,WorkAsyncComplete);

    args.GetReturnValue().Set(Undefined(isolate));

}
```

Notice the arguments to `uv_queue_work` - its the work->request we setup at the top of the function, and the two functions we have seen yet - the function to start the thread in (`WorkAsync`) and the function to call when it's complete (`WorkAsyncComplete`).

At this point, control is passed back to Node (JavaScript).  If we had further JavaScript to execute, it would execute now.  Basically, from the JavaScript side, our addon is acting the same as any other asynchronous call we typically make (like reading from files).

## The worker thread
The worker thread code is actually really simple. We just need to process the data - and since its already extracted out of the V8 objects, its pretty vanilla C++ code.  Its largely explained in [Part 3](http://blog.scottfrees.com/c-processing-from-node-js-part-3-arrays), with the exception of the cast of the `work` data.  Notice our function has been called with the libuv work request parameter.  We set this up above to point to our actual work data.

```cpp
static void WorkAsync(uv_work_t *req)
{
    Work *work = static_cast<Work *>(req->data);

    // this is the worker thread, lets build up the results
    // allocated results from the heap because we'll need
    // to access in the event loop later to send back
    work->results = new std::vector<rain_result>();
    work->results->resize(work->locations->size());
    std::transform(work->locations->begin(),
             work->locations->end(),
             work->results->begin(),
             calc_rain_stats);

    // that wasn't really that long of an operation,
    // so lets pretend it took longer...

    sleep(3);
}
```

Note - the code above also sleeps for extra effect, since the rainfall data isn't really that large in my demo.  You can remove it, or substitute it with Sleep(3000) on Windows (and replace `#include <unistd.h>` with `#include <windows.h>`).

## When the worker completes...
Once the worker thread completes, libuv handles calling our `WorkAsyncComplete` function - passing in the work request object again - so we can use it!

```cpp
// called by libuv in event loop when async function completes
static void WorkAsyncComplete(uv_work_t *req,int status)
{
    Isolate * isolate = Isolate::GetCurrent();
    Work *work = static_cast<Work *>(req->data);

    // the work has been done, and now we pack the results
    // vector into a Local array on the event-thread's stack.
    Local<Array> result_list = Array::New(isolate);
    for (unsigned int i = 0; i < work->results->size(); i++ ) {
      Local<Object> result = Object::New(isolate);
      pack_rain_result(isolate, result, (*(work->results))[i]);
      result_list->Set(i, result);
    }

    ...

```

The first part of the function above is pretty standard - we get the work data, and we package up the results into V8 objects rather than C++ vectors.  Once again, this was all discussed in more detail in [Part 3](http://blog.scottfrees.com/c-processing-from-node-js-part-3-arrays).

Next, we need to invoke the JavaScript callback that was originally passed to the addon.  **Note, this part is a lot different in Node 0.11 than it was in previous versions of Node because of recent V8 API changes.** If you are looking for ways to be a little less dependent on V8, take a look at [Nan](https://github.com/nodejs/nan).

```cpp
    // set up return arguments
    Handle<Value> argv[] = { result_list };

    // execute the callback
    Local<Function>::New(isolate, work->callback)->
      Call(isolate->GetCurrentContext()->Global(), 1, argv);

    delete work;
}
```

Once you call the callback, you're back in JavaScript!  The `print_rain_results` function will be called...

```js
rainfall.calculate_results_async(locations, function(results) {
  print_rain_results(results);
});
```

#include <Python.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

// Thread data structure
typedef struct {
    char* script_path;
    int thread_id;
} thread_data_t;

/*
 * This implementation uses Py_NewInterpreterFromConfig() with PyInterpreterConfig_OWN_GIL
 * to create completely isolated subinterpreters, each with their own GIL.
 * This allows true multi-core Python execution without GIL contention between interpreters.
 * See Python 3.12+ documentation on "Per-Interpreter GIL" for details.
 */

// Thread function to execute Python script in subinterpreter
void* execute_python_script(void* arg) {
    thread_data_t* data = (thread_data_t*)arg;
    
    printf("Thread %d starting with script: %s\n", data->thread_id, data->script_path);
    
    // Configure isolated subinterpreter with its own GIL
    PyInterpreterConfig config = {
        .use_main_obmalloc = 0,  // Use separate memory allocator
        .allow_fork = 0,         // Disable fork for safety
        .allow_exec = 0,         // Disable exec for safety  
        .allow_threads = 1,      // Allow threading
        .allow_daemon_threads = 0, // No daemon threads
        .check_multi_interp_extensions = 1, // Check extension compatibility
        .gil = PyInterpreterConfig_OWN_GIL  // Each interpreter gets its own GIL
    };
    
    // Create isolated subinterpreter
    PyThreadState* subinterp;
    PyStatus status = Py_NewInterpreterFromConfig(&subinterp, &config);
    if (PyStatus_Exception(status)) {
        fprintf(stderr, "Failed to create isolated subinterpreter for thread %d: %s\n", 
                data->thread_id, status.err_msg ? status.err_msg : "Unknown error");
        return NULL;
    }
    
    // Open and execute the Python script
    FILE* fp = fopen(data->script_path, "r");
    if (fp) {
        printf("Thread %d executing script...\n", data->thread_id);
        if (PyRun_SimpleFile(fp, data->script_path) != 0) {
            fprintf(stderr, "Error executing script %s in thread %d\n", 
                    data->script_path, data->thread_id);
        }
        fclose(fp);
    } else {
        fprintf(stderr, "Could not open script %s in thread %d\n", 
                data->script_path, data->thread_id);
    }
    
    // Clean up the subinterpreter
    Py_EndInterpreter(subinterp);
    
    printf("Thread %d completed\n", data->thread_id);
    return NULL;
}

int main() {
    printf("Python Actor Theater 3000 starting...\n");
    
    // Initialize Python interpreter with support for multiple interpreters
    PyStatus status;
    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    
    // Enable support for isolated subinterpreters
    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    
    if (PyStatus_Exception(status)) {
        fprintf(stderr, "Failed to initialize Python: %s\n", 
                status.err_msg ? status.err_msg : "Unknown error");
        return 1;
    }
    
    // Create thread data structures for sub-interpreters
    thread_data_t thread_a = {
        .script_path = "a.py",
        .thread_id = 1
    };
    
    thread_data_t thread_b = {
        .script_path = "b.py", 
        .thread_id = 2
    };
    
    // Create pthread handles
    pthread_t thread_handle_a, thread_handle_b;
    
    printf("Launching sub-interpreter threads...\n");
    
    // Launch thread A with sub-interpreter
    if (pthread_create(&thread_handle_a, NULL, execute_python_script, &thread_a) != 0) {
        fprintf(stderr, "Failed to create thread A\n");
        Py_Finalize();
        return 1;
    }
    
    // Launch thread B with sub-interpreter
    if (pthread_create(&thread_handle_b, NULL, execute_python_script, &thread_b) != 0) {
        fprintf(stderr, "Failed to create thread B\n");
        pthread_cancel(thread_handle_a);
        Py_Finalize();
        return 1;
    }
    
    // Execute main.py on the main interpreter (for signal handling)
    printf("Executing main.py on main interpreter...\n");
    FILE* fp = fopen("main.py", "r");
    if (fp) {
        if (PyRun_SimpleFile(fp, "main.py") != 0) {
            fprintf(stderr, "Error executing main.py\n");
        }
        fclose(fp);
    } else {
        fprintf(stderr, "Could not open main.py\n");
        // Still wait for threads even if main.py fails
    }
    
    // Wait for both sub-interpreter threads to complete
    printf("Waiting for sub-interpreter threads to complete...\n");
    pthread_join(thread_handle_a, NULL);
    pthread_join(thread_handle_b, NULL);
    
    printf("All threads completed. Shutting down...\n");
    
    // Finalize Python interpreter
    Py_Finalize();
    
    printf("Python Actor Theater 3000 finished.\n");
    return 0;
}

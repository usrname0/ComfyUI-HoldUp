import time 
import GPUtil # Required to get GPU temp
import sys # Required for sys.stdout for the progress bar

class HoldUp:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "latent": ("LATENT",),
                "use_waitTemperature": ("BOOLEAN", {"default": True}), # Feature is on by default
                "waitTemperature": ("INT", {"default": 50, "min": 45, "max": 90}),
                "waitSeconds": ("INT", {"default": 0, "min": 0, "max": 120}),
            }
        }

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "execute_cool_down" # Matching the method name below for clarity
    CATEGORY = "utils"

    def _display_temperature_progress(self, current_temp, target_temp, initial_peak_temp, bar_length=50):
        """
        Displays a text-based progress bar for temperature.

        Args:
            current_temp (float): The current highest temperature of the GPUs.
            target_temp (float): The target cool-down temperature (waitTemperature).
            initial_peak_temp (float): The highest temperature recorded when this 
                                     current cool-down cycle started or subsequently peaked.
            bar_length (int): The character length of the progress bar.
        """
        # Ensure target_temp is float for calculations
        target_temp = float(target_temp)

        if initial_peak_temp <= target_temp:
            # This case implies we started at or below the target.
            # If current is also low, progress is 100%. If current is somehow high, progress is 0%.
            progress = 1.0 if current_temp <= target_temp else 0.0
        elif current_temp <= target_temp:
            progress = 1.0  # Fully cooled
        else:
            # We are actively cooling from initial_peak_temp towards target_temp
            total_range_to_cool = initial_peak_temp - target_temp
            amount_cooled = initial_peak_temp - current_temp
            
            if total_range_to_cool <= 0: # Defensive check, should be covered by the first if
                progress = 1.0 if current_temp <= target_temp else 0.0
            else:
                progress = amount_cooled / total_range_to_cool
            
            progress = max(0, min(1, progress))  # Clamp progress between 0 and 1

        filled_length = int(bar_length * progress)
        bar_chars = '█' * filled_length + '-' * (bar_length - filled_length)
        
        status_message = f"***** Cooling GPUs: Peak: {initial_peak_temp:.1f}°C"
        progress_percentage = f"{progress*100:.1f}%"
        
        # \r carriage return to overwrite the line, end='' is implicitly handled by sys.stdout.write
        # Adding spaces at the end to clear any previous longer line
        full_line = f"\r{status_message} |{bar_chars}| {current_temp:.1f}°C / {target_temp:.1f}°C      "
        
        sys.stdout.write(full_line)
        sys.stdout.flush() # Ensure it's printed immediately

    def execute_cool_down(self, latent, waitSeconds, use_waitTemperature, waitTemperature): # Parameters match keys in INPUT_TYPES
        if use_waitTemperature:
            """
            Waits for GPU(s) to cool down below waitTemperature, displaying a progress bar.
            """
            initial_peak_temp_this_hot_cycle = None
            cooling_message_printed_this_cycle = False 

            while True:
                try:
                    gpus = GPUtil.getGPUs()
                except Exception as e:
                    # Handle cases where GPUtil might fail (e.g., drivers not installed)
                    print(f"\nError accessing GPU information: {e}. Skipping cool down.", file=sys.stderr)
                    return (latent,) # Exit gracefully

                if not gpus:
                    # No GPUs detected by GPUtil
                    # Depending on expected behavior, you might print a warning or just proceed
                    # print("No GPUs detected by GPUtil. Skipping cool down.") # Optional: inform user
                    break # Exit the cool down loop

                highest_current_temp = 0.0 # Initialize with a float
                any_gpu_too_hot = False

                for gpu in gpus:
                    # Ensure gpu.temperature is treated as float
                    current_gpu_temp = float(gpu.temperature)
                    if current_gpu_temp > highest_current_temp:
                        highest_current_temp = current_gpu_temp
                    if current_gpu_temp > waitTemperature:
                        any_gpu_too_hot = True
                
                if any_gpu_too_hot:
                    if initial_peak_temp_this_hot_cycle is None:
                        # This is the beginning of a new hot cycle.
                        # Record the temperature that triggered the cooldown.
                        initial_peak_temp_this_hot_cycle = highest_current_temp
                    
                    # If the temperature spikes even higher mid-cooldown, update the peak.
                    if highest_current_temp > initial_peak_temp_this_hot_cycle:
                        initial_peak_temp_this_hot_cycle = highest_current_temp

                    if not cooling_message_printed_this_cycle:
                        # sys.stdout.write("\n") # Optional: ensure progress bar starts on a new line from any prior prints
                        print(f"***** GPU temperature ({highest_current_temp:.1f}°C) exceeds target ({waitTemperature}°C). Initiating cool down...")
                        cooling_message_printed_this_cycle = True

                    # Display the progress bar. initial_peak_temp_this_hot_cycle won't be None here.
                    self._display_temperature_progress(highest_current_temp, float(waitTemperature), initial_peak_temp_this_hot_cycle)

                    time.sleep(2)  # Check every 2 seconds

                else:
                    if initial_peak_temp_this_hot_cycle is not None:
                        # We were cooling down, and now all GPUs are at or below the target.
                        # Display final 100% progress using the target temperature as the current.
                        self._display_temperature_progress(float(waitTemperature), float(waitTemperature), initial_peak_temp_this_hot_cycle)
                        sys.stdout.write("\n***** GPU cool down complete. Temperature is at or below target.\n")
                        sys.stdout.flush()
                    
                    # Reset for any future heat-up events within the same node execution (if possible)
                    initial_peak_temp_this_hot_cycle = None
                    cooling_message_printed_this_cycle = False
                    break  # Exit the while loop, cool down is complete
    
        if waitSeconds > 0:
            # Loop from the entered number of seconds down to 1
            for i in range(waitSeconds, 0, -1):
                # Print the current second
                # Use \r to return to the beginning of the line, allowing the next print to overwrite
                # Use end='' to prevent a newline character after each number
                # \r carriage return to overwrite the line, end='' is implicitly handled by sys.stdout.write
                # Adding spaces at the end to clear any previous longer line
                full_line = f"\r***** Waiting: {i} / {waitSeconds} seconds    "
                sys.stdout.write(full_line)
                sys.stdout.flush() # Ensure it's printed immediately

                # Wait for 1 second
                time.sleep(1)

            # Print the final message
            print(f"\r***** Waited: {waitSeconds} seconds         ") # Extra spaces to overwrite previous numbers

        # Print a timestamp and return the latent
        now = time.time()
        time_tuple = time.localtime(now)
        formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time_tuple)
        print(f"\r***** {formatted_time}")
        return (latent,)
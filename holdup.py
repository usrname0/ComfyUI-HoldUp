import time
import GPUtil
import sys
from comfy.comfy_types import IO


class HoldUp:
    """
    A passthrough node that pauses workflow execution to wait for GPU cooling
    and/or a fixed time delay. Accepts any input type and returns it unchanged.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input": (IO.ANY, {}),
                "use_waitTemperature": ("BOOLEAN", {"default": True}),
                "waitTemperature": ("INT", {"default": 50, "min": 45, "max": 90}),
                "waitSeconds": ("INT", {"default": 0, "min": 0, "max": 120}),
            }
        }

    RETURN_TYPES = (IO.ANY,)
    FUNCTION = "execute_cool_down"
    CATEGORY = "utils"
    OUTPUT_NODE = False

    @classmethod
    def IS_CHANGED(cls, input, use_waitTemperature, waitTemperature, waitSeconds):
        # Always execute to ensure wait happens
        return float("nan")

    def _display_temperature_progress(self, current_temp, target_temp, initial_peak_temp, bar_length=50):
        """
        Displays a text-based progress bar for GPU temperature cooldown.

        Args:
            current_temp (float): The current highest temperature of the GPUs.
            target_temp (float): The target cool-down temperature.
            initial_peak_temp (float): The highest temperature recorded when this
                                      cooldown cycle started or subsequently peaked.
            bar_length (int): The character length of the progress bar.
        """
        target_temp = float(target_temp)

        if initial_peak_temp <= target_temp:
            # Started at or below target
            progress = 1.0 if current_temp <= target_temp else 0.0
        elif current_temp <= target_temp:
            # Fully cooled
            progress = 1.0
        else:
            # Actively cooling from initial_peak_temp towards target_temp
            total_range_to_cool = initial_peak_temp - target_temp
            amount_cooled = initial_peak_temp - current_temp

            if total_range_to_cool <= 0:
                progress = 1.0 if current_temp <= target_temp else 0.0
            else:
                progress = amount_cooled / total_range_to_cool

            progress = max(0, min(1, progress))

        filled_length = int(bar_length * progress)
        bar_chars = '█' * filled_length + '-' * (bar_length - filled_length)

        status_message = f"***** Cooling GPUs: Peak: {initial_peak_temp:.1f}°C"
        full_line = f"\r{status_message} |{bar_chars}| {current_temp:.1f}°C / {target_temp:.1f}°C      "

        sys.stdout.write(full_line)
        sys.stdout.flush()

    def execute_cool_down(self, input, use_waitTemperature, waitTemperature, waitSeconds):
        """
        Waits for GPU(s) to cool down and/or a fixed time delay before returning input.

        Args:
            input: Any type of data to pass through.
            use_waitTemperature (bool): Whether to wait for GPU temperature.
            waitTemperature (int): Target temperature in Celsius.
            waitSeconds (int): Additional seconds to wait.

        Returns:
            tuple: The input data unchanged.
        """
        if use_waitTemperature:
            initial_peak_temp_this_hot_cycle = None
            cooling_message_printed_this_cycle = False

            while True:
                try:
                    gpus = GPUtil.getGPUs()
                except Exception as e:
                    print(f"\nError accessing GPU information: {e}. Skipping cool down.", file=sys.stderr)
                    return (input,)

                if not gpus:
                    # No GPUs detected, skip cooldown
                    break

                highest_current_temp = 0.0
                any_gpu_too_hot = False

                for gpu in gpus:
                    current_gpu_temp = float(gpu.temperature)
                    if current_gpu_temp > highest_current_temp:
                        highest_current_temp = current_gpu_temp
                    if current_gpu_temp > waitTemperature:
                        any_gpu_too_hot = True

                if any_gpu_too_hot:
                    if initial_peak_temp_this_hot_cycle is None:
                        initial_peak_temp_this_hot_cycle = highest_current_temp

                    # Update peak if temperature spikes higher mid-cooldown
                    if highest_current_temp > initial_peak_temp_this_hot_cycle:
                        initial_peak_temp_this_hot_cycle = highest_current_temp

                    if not cooling_message_printed_this_cycle:
                        print(f"***** GPU temperature ({highest_current_temp:.1f}°C) exceeds target ({waitTemperature}°C). Initiating cool down...")
                        cooling_message_printed_this_cycle = True

                    self._display_temperature_progress(highest_current_temp, float(waitTemperature), initial_peak_temp_this_hot_cycle)
                    time.sleep(2)
                else:
                    if initial_peak_temp_this_hot_cycle is not None:
                        # Display final 100% progress
                        self._display_temperature_progress(float(waitTemperature), float(waitTemperature), initial_peak_temp_this_hot_cycle)
                        sys.stdout.write("\n***** GPU cool down complete. Temperature is at or below target.\n")
                        sys.stdout.flush()

                    initial_peak_temp_this_hot_cycle = None
                    cooling_message_printed_this_cycle = False
                    break

        if waitSeconds > 0:
            for i in range(waitSeconds, 0, -1):
                full_line = f"\r***** Waiting: {i} / {waitSeconds} seconds    "
                sys.stdout.write(full_line)
                sys.stdout.flush()
                time.sleep(1)

            print(f"\r***** Waited: {waitSeconds} seconds         ")

        # Print timestamp and return input unchanged
        now = time.time()
        time_tuple = time.localtime(now)
        formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time_tuple)
        print(f"\r***** {formatted_time}")
        return (input,)

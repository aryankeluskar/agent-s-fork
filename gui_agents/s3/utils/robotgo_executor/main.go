package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"strings"

	"github.com/go-vgo/robotgo"
)

// Action represents a GUI action command
// Based on patterns from the turing project (https://github.com/sohamd22/turing)
type Action struct {
	Type     string                 `json:"type"`
	Params   map[string]interface{} `json:"params"`
	Platform string                 `json:"platform,omitempty"`
}

// normalizeKey normalizes key names for the current platform
func normalizeKey(key string, platform string) string {
	keyLower := strings.ToLower(key)

	switch platform {
	case "darwin":
		keyMap := map[string]string{
			"cmd":  "cmd",
			"win":  "cmd",
			"opt":  "alt",
			"meta": "cmd",
		}
		if normalized, ok := keyMap[keyLower]; ok {
			return normalized
		}
	case "windows":
		keyMap := map[string]string{
			"command": "win",
			"cmd":     "win",
			"opt":     "alt",
			"option":  "alt",
			"meta":    "win",
		}
		if normalized, ok := keyMap[keyLower]; ok {
			return normalized
		}
	case "linux":
		keyMap := map[string]string{
			"command": "super",
			"cmd":     "super",
			"win":     "super",
			"opt":     "alt",
			"option":  "alt",
			"meta":    "super",
		}
		if normalized, ok := keyMap[keyLower]; ok {
			return normalized
		}
	}
	return key
}

// executeAction executes a GUI action using robotgo
func executeAction(action Action) error {
	platform := action.Platform
	if platform == "" {
		platform = runtime.GOOS
	}

	switch action.Type {
	case "click":
		x, _ := getFloat(action.Params["x"])
		y, _ := getFloat(action.Params["y"])
		if x < 0 || y < 0 {
			return fmt.Errorf("invalid coordinates: x=%v, y=%v", x, y)
		}
		clicks := 1
		if c, ok := action.Params["clicks"]; ok {
			if ci, ok := c.(float64); ok {
				clicks = int(ci)
			} else if ci, ok := c.(int); ok {
				clicks = ci
			}
		}
		button := "left"
		if b, ok := action.Params["button"]; ok {
			button = fmt.Sprintf("%v", b)
		}

		// Hold modifier keys if specified
		if holdKeys, ok := action.Params["hold_keys"]; ok {
			if keys, ok := holdKeys.([]interface{}); ok {
				for _, k := range keys {
					key := normalizeKey(fmt.Sprintf("%v", k), platform)
					robotgo.KeyToggle(key, "down")
				}
			}
		}

		// Move to position first (like turing does)
		robotgo.Move(int(x), int(y))
		robotgo.MilliSleep(100) // Small delay to ensure movement completes

		// Perform click(s) - use double click for clicks > 1
		if clicks == 1 {
			if button == "right" {
				robotgo.Click("right")
			} else {
				robotgo.Click()
			}
		} else if clicks == 2 {
			robotgo.Click("left", true) // double click
		} else {
			// For more clicks, do multiple single clicks
			for i := 0; i < clicks; i++ {
				robotgo.Click()
				if i < clicks-1 {
					robotgo.MilliSleep(50)
				}
			}
		}

		// Release modifier keys
		if holdKeys, ok := action.Params["hold_keys"]; ok {
			if keys, ok := holdKeys.([]interface{}); ok {
				for _, k := range keys {
					key := normalizeKey(fmt.Sprintf("%v", k), platform)
					robotgo.KeyToggle(key, "up")
				}
			}
		}

	case "moveTo":
		x, _ := getFloat(action.Params["x"])
		y, _ := getFloat(action.Params["y"])
		if x < 0 || y < 0 {
			return fmt.Errorf("invalid coordinates: x=%v, y=%v", x, y)
		}
		robotgo.Move(int(x), int(y))

	case "dragTo":
		x1, _ := getFloat(action.Params["x1"])
		y1, _ := getFloat(action.Params["y1"])
		x2, _ := getFloat(action.Params["x2"])
		y2, _ := getFloat(action.Params["y2"])
		if x1 < 0 || y1 < 0 || x2 < 0 || y2 < 0 {
			return fmt.Errorf("invalid drag coordinates: (%v,%v) to (%v,%v)", x1, y1, x2, y2)
		}
		// button parameter currently unused by robotgo.Drag
		// button := "left"
		// if b, ok := action.Params["button"]; ok {
		// 	button = fmt.Sprintf("%v", b)
		// }

		// Hold modifier keys if specified
		if holdKeys, ok := action.Params["hold_keys"]; ok {
			if keys, ok := holdKeys.([]interface{}); ok {
				for _, k := range keys {
					key := normalizeKey(fmt.Sprintf("%v", k), platform)
					robotgo.KeyToggle(key, "down")
				}
			}
		}

		// Move to start position first (robotgo.Drag drags from current position)
		robotgo.Move(int(x1), int(y1))
		robotgo.MilliSleep(100)

		// Drag to end position (robotgo.Drag takes absolute coordinates)
		robotgo.Drag(int(x2), int(y2))

		// Release modifier keys
		if holdKeys, ok := action.Params["hold_keys"]; ok {
			if keys, ok := holdKeys.([]interface{}); ok {
				for _, k := range keys {
					key := normalizeKey(fmt.Sprintf("%v", k), platform)
					robotgo.KeyToggle(key, "up")
				}
			}
		}

	case "type", "write":
		text, _ := action.Params["text"].(string)
		robotgo.TypeStr(text)

	case "press":
		key, _ := action.Params["key"].(string)
		key = normalizeKey(key, platform)
		robotgo.KeyTap(key)

	case "hotkey":
		keys, ok := action.Params["keys"].([]interface{})
		if !ok {
			return fmt.Errorf("hotkey requires 'keys' array")
		}
		if len(keys) == 0 {
			return fmt.Errorf("hotkey requires at least one key")
		}

		normalizedKeys := make([]string, len(keys))
		for i, k := range keys {
			normalizedKeys[i] = normalizeKey(fmt.Sprintf("%v", k), platform)
		}

		// robotgo.KeyTap takes the main key first, then modifiers
		if len(normalizedKeys) == 1 {
			robotgo.KeyTap(normalizedKeys[0])
		} else {
			// Last key is the main key, rest are modifiers
			mainKey := normalizedKeys[len(normalizedKeys)-1]
			modifiers := normalizedKeys[:len(normalizedKeys)-1]
			// Convert []string to []interface{} for robotgo v1.0.0
			modifiersInterface := make([]interface{}, len(modifiers))
			for i, m := range modifiers {
				modifiersInterface[i] = m
			}
			robotgo.KeyTap(mainKey, modifiersInterface...)
			robotgo.MilliSleep(50)
			// Ensure modifiers are released
			for _, modifier := range modifiers {
				robotgo.KeyToggle(modifier, "up")
			}
		}

	case "keyDown":
		key, _ := action.Params["key"].(string)
		key = normalizeKey(key, platform)
		robotgo.KeyToggle(key, "down")

	case "keyUp":
		key, _ := action.Params["key"].(string)
		key = normalizeKey(key, platform)
		robotgo.KeyToggle(key, "up")

	case "scroll":
		x, _ := getFloat(action.Params["x"])
		y, _ := getFloat(action.Params["y"])
		clicks, _ := getFloat(action.Params["clicks"])
		if x < 0 || y < 0 {
			return fmt.Errorf("invalid scroll coordinates: x=%v, y=%v", x, y)
		}
		horizontal := false
		if h, ok := action.Params["horizontal"]; ok {
			if hb, ok := h.(bool); ok {
				horizontal = hb
			}
		}

		// Move to position first
		robotgo.Move(int(x), int(y))
		robotgo.MilliSleep(500)

		// robotgo.Scroll takes (x, y int) where:
		// - y positive = scroll down, y negative = scroll up
		// - x positive = scroll right, x negative = scroll left
		// clicks can be positive (down/right) or negative (up/left)
		scrollAmount := int(clicks)
		if horizontal {
			robotgo.Scroll(scrollAmount, 0)
		} else {
			robotgo.Scroll(0, scrollAmount)
		}

	case "wait":
		duration, _ := getFloat(action.Params["duration"])
		// Convert seconds to milliseconds for MilliSleep
		ms := int(duration * 1000)
		robotgo.MilliSleep(ms)

	case "screenSize":
		// Return screen size as JSON
		w, h := robotgo.GetScreenSize()
		fmt.Printf(`{"width":%d,"height":%d}`, w, h)
		return nil

	default:
		return fmt.Errorf("unknown action type: %s", action.Type)
	}

	return nil
}

func getFloat(v interface{}) (float64, error) {
	switch val := v.(type) {
	case float64:
		return val, nil
	case int:
		return float64(val), nil
	case string:
		return strconv.ParseFloat(val, 64)
	default:
		return 0, fmt.Errorf("cannot convert %v to float64", v)
	}
}

func main() {
	var jsonInput string
	var platform string
	flag.StringVar(&jsonInput, "json", "", "JSON action to execute")
	flag.StringVar(&platform, "platform", "", "Platform (darwin, windows, linux)")
	flag.Parse()

	if jsonInput == "" {
		// Try reading from stdin
		var input []byte
		fmt.Scanln(&input)
		jsonInput = string(input)
	}

	if jsonInput == "" {
		fmt.Fprintf(os.Stderr, "Error: No JSON input provided\n")
		os.Exit(1)
	}

	var action Action
	if err := json.Unmarshal([]byte(jsonInput), &action); err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing JSON: %v\n", err)
		os.Exit(1)
	}

	if platform != "" {
		action.Platform = platform
	}

	if err := executeAction(action); err != nil {
		fmt.Fprintf(os.Stderr, "Error executing action: %v\n", err)
		os.Exit(1)
	}
}

"""
Agent-S Voice Command

Voice-activated assistant with:
- Wake word detection ("Hey Jarvis")
- Real-time transcription
- Transparent overlay UI
"""

import sys


def cmd_voice_start(args):
    """Start the voice assistant."""
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        print("❌ PyQt5 not installed. Install with: pip install PyQt5 PyQtWebEngine")
        return 1
    
    try:
        from gui_agents.s3.voice.assistant import VoiceAssistant
        from gui_agents.s3.voice.overlay import TransparentOverlay, start_http_server
    except ImportError as e:
        print(f"❌ Voice module dependencies missing: {e}")
        print("Install with: pip install openwakeword pyaudio numpy websockets")
        return 1
    
    import os
    
    # Check for API key
    if not os.environ.get("WISPR_API_KEY"):
        print("⚠️  Warning: WISPR_API_KEY not set. Transcription may not work.")
    
    port = 8765
    
    print("\n" + "=" * 60)
    print("🎤 Agent-S Voice Assistant")
    print("=" * 60)
    print("Wake word: 'Hey Jarvis'")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    # Start local HTTP server for orb.html
    try:
        server = start_http_server(port)
    except Exception as e:
        print(f"⚠️  Could not start HTTP server: {e}")
        server = None
    
    app = QApplication(sys.argv)
    
    # Create overlay with HTTP port
    overlay = TransparentOverlay(http_port=port)
    
    # Create voice assistant with optional device selection
    assistant = VoiceAssistant(overlay, input_device_index=args.device)
    assistant.start()
    
    # Cleanup on exit
    app.aboutToQuit.connect(assistant.cleanup)
    
    try:
        return app.exec_()
    finally:
        if server:
            server.shutdown()


def cmd_voice_list_devices(args):
    """List available audio input devices."""
    try:
        import pyaudio
    except ImportError:
        print("❌ pyaudio not installed. Install with: pip install pyaudio")
        return 1
    
    audio = pyaudio.PyAudio()
    
    print("\n" + "=" * 60)
    print("🎤 Available Audio Input Devices")
    print("=" * 60 + "\n")
    
    device_count = 0
    for i in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            device_count += 1
            print(f"  [{i}] {info['name']}")
            print(f"      Channels: {info['maxInputChannels']}, Sample Rate: {int(info['defaultSampleRate'])}Hz")
    
    audio.terminate()
    
    if device_count == 0:
        print("  No input devices found!")
    
    print("\n" + "-" * 60)
    print("Usage: agent_s voice start --device <index>")
    print("       agent_s voice start  (auto-selects microphone)")
    print("-" * 60 + "\n")
    
    return 0


def add_voice_arguments(parser):
    """Add arguments for the voice command."""
    subparsers = parser.add_subparsers(dest="voice_action", help="Voice actions")
    
    # Start subcommand
    start_parser = subparsers.add_parser("start", help="Start voice assistant")
    start_parser.add_argument(
        "--device", "-d",
        type=int,
        default=None,
        help="Audio input device index (use list-devices to see available)",
    )
    
    # List devices subcommand
    subparsers.add_parser("list-devices", help="List available audio input devices")


def cmd_voice(args):
    """Handle voice command dispatch."""
    if not hasattr(args, "voice_action") or args.voice_action is None:
        print("Usage: agent_s voice {start|list-devices}")
        print("\nCommands:")
        print("  start         Start the voice assistant")
        print("  list-devices  List available audio input devices")
        return 1
    
    if args.voice_action == "start":
        return cmd_voice_start(args)
    elif args.voice_action == "list-devices":
        return cmd_voice_list_devices(args)
    else:
        print(f"Unknown voice action: {args.voice_action}")
        return 1

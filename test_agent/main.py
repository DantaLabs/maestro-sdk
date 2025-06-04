#!/usr/bin/env python3
"""
Simple test agent for bundle functionality.
"""

def main():
    """Main entry point for the agent."""
    print("Hello from test agent!")
    
    # Simple processing
    message = "Test message from agent"
    result = {
        "status": "success",
        "message": message,
        "data": {
            "processed": True,
            "timestamp": "2024-01-01T00:00:00Z"
        }
    }
    
    print(f"Agent result: {result}")
    return result

if __name__ == "__main__":
    main() 
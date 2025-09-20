#!/usr/bin/env python3
"""
Sample script demonstrating DantaLabs Maestro SDK usage.
This script shows how to interact with existing agents, manage memory, and execute tasks.
"""

import os
import json
from typing import Dict, Any, List
from dantalabs.maestro import MaestroClient
from dantalabs.maestro.exceptions import MaestroError, MaestroApiError
from dotenv import load_dotenv

load_dotenv()

# Environment variables for authentication
ORGANIZATION_ID = os.getenv("ORGANIZATION_ID")
BASE_URL = os.getenv("BASE_URL")
DANTA_API_KEY = os.getenv("DANTA_API_KEY")


def main():
    """Main function demonstrating various SDK features."""

    # Initialize the Maestro client
    try:
        client = MaestroClient(
            organization_id=ORGANIZATION_ID, base_url=BASE_URL, token=DANTA_API_KEY
        )
        print("Successfully initialized Maestro client")
    except Exception as e:
        print(f"Failed to initialize client: {e}")
        return

    try:
        # 1. List all available agents
        print("\nFetching available agents...")
        agents = client.list_agents()

        if not agents:
            print("No agents found in this organization")
            return

        print(f"Found {len(agents)} agent(s):")
        for i, agent in enumerate(agents):
            print(f"  {i+1}. {agent.name} (ID: {agent.id}) - Type: {agent.agent_type}")

        # 2. Select the first agent for demonstration
        selected_agent = agents[0]
        print(f"\nUsing agent: {selected_agent.name}")
        print(f"   Agent ID: {selected_agent.id}")

        # 3. Get agent details and definition
        print(f"\nAgent Details:")
        print(f"  Name: {selected_agent.name}")
        print(f"  Description: {selected_agent.description or 'No description'}")
        print(f"  Type: {selected_agent.agent_type}")
        print(f"  Created: {selected_agent.created_at}")

        # Get agent definition for more details
        if selected_agent.agent_definition_id:
            definition = client.get_agent_definition(selected_agent.agent_definition_id)
            print(f"  Definition Type: {definition.definition_type}")
            print(f"  Is Bundle: {definition.is_bundle}")

        # 4. Execute the agent with sample input
        print(f"\nExecuting agent '{selected_agent.name}'...")

        # Prepare sample input - adjust this based on your agent's expected input
        sample_input = {
            "message": "Hello from the SDK sample script!",
            "task": "process_request",
            "data": {"timestamp": "2024-01-01T12:00:00Z", "user_id": "sample_user"},
        }

        print(f"Input data: {json.dumps(sample_input, indent=2)}")

        # Execute synchronously
        try:
            # Try direct execution first, with debugging info
            print(f"Debug: Calling execute_agent_code_sync with:")
            print(f"   - variables type: {type(sample_input)}")
            print(
                f"   - agent_id: {selected_agent.id} (type: {type(selected_agent.id)})"
            )

            # Use explicit keyword arguments to avoid any parameter confusion
            execution_result = client.execute_agent_code_sync(
                variables=sample_input, agent_id=selected_agent.id
            )

            print(f"Execution completed!")
            print(f"Status: {execution_result.status}")
            print(f"Execution ID: {execution_result.id}")
            print(f"Duration: {execution_result.duration}s")

            if execution_result.execution_result:
                print(
                    f"Result: {json.dumps(execution_result.execution_result, indent=2)}"
                )

        except TypeError as e:
            print(f"Type/Parameter Error during execution: {e}")
            print(f"   This suggests a method signature mismatch.")
            print(f"   Trying alternative approach...")

            # Try using the agents resource directly as a workaround
            try:
                print(f"Attempting direct resource call...")
                execution_result = client.agents.execute_code_sync(
                    sample_input, selected_agent.id
                )
                print(f"Direct execution successful!")
                print(f"Status: {execution_result.status}")
                if execution_result.execution_result:
                    print(
                        f"Result: {json.dumps(execution_result.execution_result, indent=2)}"
                    )
            except Exception as e2:
                print(f"Direct execution also failed: {e2}")

        except MaestroApiError as e:
            print(f"API Error during execution: {e}")
        except Exception as e:
            print(f"Execution failed: {e}")
            print(f"   Error type: {type(e)}")

        # 5. Demonstrate managed memory usage
        print(f"\nDemonstrating managed memory...")
        try:
            # Get managed memory for the agent
            memory = client.get_managed_memory(
                memory_name="session_data",
                agent_id=selected_agent.id,
                create_if_missing=True,
            )

            # Store some data
            memory["last_execution"] = {
                "timestamp": "2024-01-01T12:00:00Z",
                "input_keys": list(sample_input.keys()),
                "status": "completed",
            }

            memory["user_preferences"] = {"format": "json", "verbose": True}

            # Save changes using merge strategy (safer for partial updates)
            success = memory.commit_with_strategy("merge")
            if success:
                print("Memory data saved successfully")
            else:
                print("Failed to save memory data")

            # Read back the data
            print(f"Memory contents: {dict(memory)}")

        except Exception as e:
            print(f"Memory operation failed: {e}")

        # 6. List recent executions
        print(f"\nRecent executions:")
        try:
            # Try without agent_id first (organization-wide), then with agent_id if that fails
            try:
                recent_executions = client.list_executions(limit=5, skip=0)
                print(f"  Listing organization-wide executions")
            except Exception:
                # Fallback to agent-specific executions
                recent_executions = client.list_executions(
                    limit=5, skip=0, agent_id=selected_agent.id
                )
                print(f"  Listing executions for agent: {selected_agent.name}")

            if recent_executions:
                for exec in recent_executions[:3]:  # Show last 3
                    print(f"  - {exec.id}: {exec.status} ({exec.executed_at})")
            else:
                print("  No recent executions found")

        except Exception as e:
            print(f"Failed to list executions: {e}")
            print(
                f"   This might be expected if the API requires additional parameters"
            )

        # 7. Check if agent has databases
        print(f"\nChecking agent databases...")
        try:
            databases = client.list_agent_databases(selected_agent.id)

            if databases:
                print(f"Found {len(databases)} database(s):")
                for db in databases:
                    print(f"  - {db.name}: {db.description or 'No description'}")
            else:
                print("  No databases found for this agent")

        except Exception as e:
            print(f"Failed to list databases: {e}")

        # 8. Try querying the agent using direct execution
        print(f"\nTesting direct agent execution...")
        try:
            query_input = {"query": "What can you do?", "context": "SDK testing"}

            # Use direct execution instead of the query_agent method
            result = client.execute_agent_code_sync(
                variables=query_input, agent_id=selected_agent.id
            )

            print("Direct execution successful!")
            print(f"Status: {result.status}")
            if result.execution_result:
                print(f"Result: {json.dumps(result.execution_result, indent=2)}")

        except Exception as e:
            print(f"Direct execution failed: {e}")

        # 9. Multi-agent demonstration (if multiple agents exist)
        if len(agents) > 1:
            print(f"\nMulti-agent demonstration:")
            demonstrate_multi_agent_usage(client, agents[:3])  # Use up to 3 agents
        else:
            print(
                f"\nSkipping multi-agent demo - only {len(agents)} agent(s) available"
            )

        # 10. Network generation demonstration
        print(f"\nNetwork generation demonstration:")
        try:
            demonstrate_network_generation(client, agents)
        except Exception as e:
            print(f"Network generation demonstration failed: {e}")

        # 11. Advanced orchestration patterns
        if len(agents) >= 2:
            print(f"\nAdvanced orchestration patterns:")
            try:
                demonstrate_orchestration_patterns(client, agents)
            except Exception as e:
                print(f"Orchestration patterns demonstration failed: {e}")
        else:
            print(
                f"\nSkipping orchestration patterns - need at least 2 agents, have {len(agents)}"
            )

        print(f"\nSample script completed successfully!")

    except MaestroError as e:
        print(f"Maestro SDK Error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        # Clean up client connections
        client.close()
        print("\nClient connections closed")


def demonstrate_multi_agent_usage(client: MaestroClient, agents):
    """Demonstrate coordinated usage of multiple agents."""
    print(f"Working with {len(agents)} agents:")

    # Show agent capabilities
    for i, agent in enumerate(agents):
        print(f"  {i+1}. {agent.name} (Type: {agent.agent_type})")

    # Execute multiple agents in sequence
    print(f"\nExecuting agents in sequence:")
    results = []

    for i, agent in enumerate(agents):
        try:
            # Customize input based on agent type
            if "data" in agent.name.lower() or "process" in agent.name.lower():
                input_data = {
                    "data": f"Sample data from multi-agent demo - Agent {i+1}",
                    "source": "multi_agent_sequence",
                }
            elif "chat" in agent.name.lower() or "conversation" in agent.name.lower():
                input_data = {
                    "message": f"Hello from multi-agent demo, I'm agent {i+1}",
                    "context": "multi_agent_coordination",
                }
            else:
                input_data = {
                    "task": f"multi_agent_task_{i+1}",
                    "agent_sequence": i + 1,
                    "total_agents": len(agents),
                }

            print(f"  Executing {agent.name}...")
            result = client.execute_agent_code_sync(
                variables=input_data, agent_id=agent.id
            )

            results.append(
                {
                    "agent": agent.name,
                    "agent_id": str(agent.id),
                    "status": result.status,
                    "result": result.execution_result,
                }
            )

            print(f"    Status: {result.status}")

        except Exception as e:
            print(f"    Failed: {e}")
            results.append(
                {
                    "agent": agent.name,
                    "agent_id": str(agent.id),
                    "status": "failed",
                    "error": str(e),
                }
            )

    # Show coordination summary
    print(f"\nMulti-agent execution summary:")
    successful = [r for r in results if r["status"] not in ["failed", "error"]]
    failed = [r for r in results if r["status"] in ["failed", "error"]]

    print(f"  Successful executions: {len(successful)}")
    print(f"  Failed executions: {len(failed)}")

    if successful:
        print(f"  Successful agents:")
        for result in successful:
            print(f"    - {result['agent']}: {result['status']}")

    # Demonstrate agent memory sharing (conceptual)
    if len(successful) >= 2:
        print(f"\nDemonstrating shared memory between agents:")
        try:
            # Use shared memory name for coordination
            shared_memory = client.get_managed_memory(
                memory_name="multi_agent_shared",
                agent_id=successful[0]["agent_id"],  # Use first successful agent
                create_if_missing=True,
            )

            # Store coordination data
            shared_memory["execution_sequence"] = [r["agent"] for r in successful]
            shared_memory["coordination_timestamp"] = "2024-01-01T12:00:00Z"
            shared_memory["results_summary"] = {
                "total_executed": len(results),
                "successful": len(successful),
                "failed": len(failed),
            }

            success = shared_memory.commit_with_strategy("merge")
            if success:
                print(f"  Shared memory updated successfully")
                print(f"  Coordination data: {dict(shared_memory)}")
            else:
                print(f"  Failed to update shared memory")

        except Exception as e:
            print(f"  Shared memory demonstration failed: {e}")


def demonstrate_network_generation(client: MaestroClient, agents):
    """Demonstrate network generation and management capabilities."""
    from dantalabs.maestro.models import NetworkGenerationRequest

    print(f"Generating agent networks:")

    # Check if network generation is available by testing credentials/permissions
    try:
        # Try to list existing networks first to test permissions
        test_networks = client.list_networks(limit=1)
        network_generation_available = True
        print(f"  Network operations available")
    except Exception as e:
        network_generation_available = False
        if "403" in str(e) or "Could not validate credentials" in str(e):
            print(f"  Network generation not available - insufficient permissions")
            print(
                f"  This feature may require additional API access or enterprise features"
            )
        else:
            print(f"  Network operations unavailable: {e}")
        print(f"  Skipping network generation demonstration")

        # Show what would be demonstrated if networks were available
        print(f"\n  Network Generation Features (when available):")
        print(f"    - Data Processing Pipeline creation")
        print(f"    - Collaborative Chat System design")
        print(f"    - Multi-step Workflow orchestration")
        print(f"    - Network node and connection management")
        print(f"    - Network lifecycle operations")
        return

    # Create different types of network prompts
    network_prompts = [
        {
            "name": "Data Processing Pipeline",
            "prompt": f"Create a data processing pipeline using these agents: {', '.join([a.name for a in agents[:3]])}. The pipeline should flow from data ingestion through processing to output.",
            "use_case": "data_pipeline",
        },
        {
            "name": "Collaborative Chat System",
            "prompt": f"Design a collaborative system where agents {', '.join([a.name for a in agents[:2]])} can work together to handle complex user queries through conversation and task delegation.",
            "use_case": "collaborative_chat",
        },
        {
            "name": "Multi-step Workflow",
            "prompt": f"Create a workflow network that coordinates between {len(agents)} agents for handling complex multi-step tasks with error handling and retry mechanisms.",
            "use_case": "workflow_automation",
        },
    ]

    generated_networks = []

    for i, network_spec in enumerate(
        network_prompts[:2]
    ):  # Limit to 2 to avoid too many API calls
        try:
            print(f"\n  Generating network: {network_spec['name']}")
            print(f"    Prompt: {network_spec['prompt'][:100]}...")

            # Create network generation request
            request = NetworkGenerationRequest(prompt=network_spec["prompt"])

            # Generate the network
            network_response = client.generate_network(request)

            print(f"    Generated network ID: {network_response.id}")
            print(f"    Network name: {network_response.name}")
            print(
                f"    Description: {network_response.description or 'No description'}"
            )
            print(f"    Nodes: {len(network_response.nodes)}")
            print(f"    Connections: {len(network_response.connections)}")

            # Store network info
            generated_networks.append(
                {
                    "name": network_spec["name"],
                    "network_id": network_response.id,
                    "nodes": len(network_response.nodes),
                    "connections": len(network_response.connections),
                    "use_case": network_spec["use_case"],
                }
            )

            # Show network structure
            if network_response.nodes:
                print(f"    Network nodes:")
                for node in network_response.nodes[:3]:  # Show first 3 nodes
                    print(f"      - Node {node.id}: Agent {node.agent_id}")

            if network_response.connections:
                print(f"    Network connections:")
                for conn in network_response.connections[
                    :3
                ]:  # Show first 3 connections
                    print(f"      - {conn.source_node_id} -> {conn.target_node_id}")

        except Exception as e:
            print(f"    Failed to generate network '{network_spec['name']}': {e}")
            generated_networks.append(
                {
                    "name": network_spec["name"],
                    "error": str(e),
                    "use_case": network_spec["use_case"],
                }
            )

    # List existing networks
    print(f"\nListing existing networks:")
    try:
        existing_networks = client.list_networks(limit=5)
        if existing_networks.networks:
            print(f"  Found {len(existing_networks.networks)} existing network(s):")
            for network in existing_networks.networks:
                print(f"    - {network.name} (ID: {network.id})")
                print(f"      Created: {network.created_at}")
                print(
                    f"      Nodes: {len(network.nodes)}, Connections: {len(network.connections)}"
                )
        else:
            print(f"  No existing networks found")

    except Exception as e:
        print(f"  Failed to list networks: {e}")

    # Network management demonstration
    if generated_networks and any("network_id" in net for net in generated_networks):
        print(f"\nNetwork management demonstration:")

        # Get details of first successfully generated network
        successful_nets = [net for net in generated_networks if "network_id" in net]
        if successful_nets:
            first_network = successful_nets[0]
            try:
                print(f"  Getting details for network: {first_network['name']}")
                network_details = client.get_network(first_network["network_id"])

                print(
                    f"    Network metadata: {network_details.network_metadata or 'None'}"
                )
                print(f"    Organization: {network_details.organization_id}")
                print(f"    Last updated: {network_details.updated_at}")

                # Demonstrate network cleanup (optional - commented out to avoid deleting demo networks)
                # print(f"  Cleaning up demo network...")
                # client.delete_network(first_network['network_id'])
                # print(f"    Network deleted successfully")

            except Exception as e:
                print(f"    Network management failed: {e}")

    # Summary
    print(f"\nNetwork generation summary:")
    successful_gens = [net for net in generated_networks if "network_id" in net]
    failed_gens = [net for net in generated_networks if "error" in net]

    print(f"  Successfully generated: {len(successful_gens)} networks")
    print(f"  Failed generations: {len(failed_gens)}")

    if successful_gens:
        print(f"  Generated networks:")
        for net in successful_gens:
            print(
                f"    - {net['name']}: {net['nodes']} nodes, {net['connections']} connections"
            )


def demonstrate_orchestration_patterns(client: MaestroClient, agents):
    """Demonstrate advanced multi-agent orchestration patterns."""

    # Pattern 1: Pipeline Processing
    print(f"  Pattern 1: Sequential Pipeline Processing")
    try:
        pipeline_data = "Initial data for pipeline processing"
        pipeline_results = []

        for i, agent in enumerate(agents[:3]):
            input_data = {
                "data": pipeline_data if i == 0 else f"Processed data from stage {i}",
                "stage": i + 1,
                "pipeline_id": "demo_pipeline_001",
                "previous_results": pipeline_results,
            }

            print(f"    Stage {i+1}: Processing with {agent.name}")
            result = client.execute_agent_code_sync(
                variables=input_data, agent_id=agent.id
            )

            pipeline_results.append(
                {
                    "stage": i + 1,
                    "agent": agent.name,
                    "status": result.status,
                    "output": result.execution_result,
                }
            )

            print(f"      Status: {result.status}")

        print(f"    Pipeline completed with {len(pipeline_results)} stages")

    except Exception as e:
        print(f"    Pipeline pattern failed: {e}")

    # Pattern 2: Parallel Processing with Aggregation
    print(f"\n  Pattern 2: Parallel Processing with Aggregation")
    try:
        # Execute multiple agents in parallel (conceptually)
        parallel_task = {
            "task_id": "parallel_demo_001",
            "data_chunk": "Sample data chunk for parallel processing",
            "coordination": True,
        }

        parallel_results = []
        for i, agent in enumerate(agents[:3]):
            task_data = {
                **parallel_task,
                "worker_id": i + 1,
                "chunk_id": f"chunk_{i+1}",
            }

            print(f"    Worker {i+1}: {agent.name}")
            result = client.execute_agent_code_sync(
                variables=task_data, agent_id=agent.id
            )

            parallel_results.append(
                {
                    "worker": i + 1,
                    "agent": agent.name,
                    "status": result.status,
                    "result": result.execution_result,
                }
            )

        # Aggregation step (use first agent as aggregator)
        if parallel_results and agents:
            print(f"    Aggregation: Using {agents[0].name} as aggregator")
            aggregation_input = {
                "operation": "aggregate_results",
                "parallel_results": parallel_results,
                "task_id": parallel_task["task_id"],
            }

            final_result = client.execute_agent_code_sync(
                variables=aggregation_input, agent_id=agents[0].id
            )

            print(f"      Aggregation status: {final_result.status}")

    except Exception as e:
        print(f"    Parallel pattern failed: {e}")

    # Pattern 3: Decision Tree / Conditional Routing
    print(f"\n  Pattern 3: Conditional Agent Routing")
    try:
        # Simulate different types of requests that route to different agents
        request_types = [
            {"type": "data_analysis", "complexity": "high"},
            {"type": "text_processing", "complexity": "medium"},
            {"type": "simple_task", "complexity": "low"},
        ]

        for req_type in request_types[: len(agents)]:
            # Route based on agent capabilities (simulated)
            selected_agent = agents[hash(req_type["type"]) % len(agents)]

            routing_input = {
                "request_type": req_type["type"],
                "complexity": req_type["complexity"],
                "routing_decision": f"routed_to_{selected_agent.name}",
                "original_request": "Sample request for conditional routing",
            }

            print(f"    Route: {req_type['type']} -> {selected_agent.name}")
            result = client.execute_agent_code_sync(
                variables=routing_input, agent_id=selected_agent.id
            )

            print(f"      Status: {result.status}")

    except Exception as e:
        print(f"    Routing pattern failed: {e}")

    # Pattern 4: Agent Memory Coordination
    print(f"\n  Pattern 4: Cross-Agent Memory Coordination")
    try:
        coordination_memory = client.get_managed_memory(
            memory_name="orchestration_coordination",
            agent_id=agents[0].id,
            create_if_missing=True,
        )

        # Store orchestration state
        coordination_memory["active_patterns"] = [
            "pipeline_processing",
            "parallel_aggregation",
            "conditional_routing",
        ]
        coordination_memory["agent_registry"] = [
            {"id": str(agent.id), "name": agent.name, "type": agent.agent_type}
            for agent in agents[:3]
        ]
        coordination_memory["execution_timestamp"] = "2024-01-01T12:00:00Z"

        success = coordination_memory.commit_with_strategy("merge")
        if success:
            print(f"    Coordination memory updated successfully")
            print(f"    Registered {len(coordination_memory['agent_registry'])} agents")
        else:
            print(f"    Failed to update coordination memory")

    except Exception as e:
        print(f"    Memory coordination failed: {e}")


def demonstrate_service_operations(client: MaestroClient, agent_id):
    """Demonstrate service-related operations (optional)."""
    print(f"\nService Operations Demo:")

    try:
        # Check deployment status
        status = client.get_deployment_status(agent_id)
        print(f"Deployment Status: {status}")

        # List all services
        services = client.list_services()
        print(f"Active Services: {len(services)}")

        # Get service logs (if available)
        logs = client.get_service_logs(agent_id, limit=10)
        if logs:
            print(f"Recent logs: {len(logs)} entries")
            for log in logs[-3:]:  # Show last 3 logs
                print(f"  {log.get('timestamp', 'N/A')}: {log.get('message', 'N/A')}")

    except Exception as e:
        print(f"Service operations failed: {e}")


def health_check_demo(client: MaestroClient):
    """Demonstrate health check and utility functions."""
    print(f"\nHealth Check Demo:")

    try:
        # Perform health check
        is_healthy = client.health_check()
        print(f"API Health: {'Healthy' if is_healthy else 'Unhealthy'}")

        # List organization details
        org_details = client.read_organization()
        print(f"Organization: {org_details.name}")
        print(f"Members: {len(client.get_organization_members())}")

    except Exception as e:
        print(f"Health check failed: {e}")


if __name__ == "__main__":
    # Verify environment variables
    if not all([ORGANIZATION_ID, BASE_URL, DANTA_API_KEY]):
        print("Missing required environment variables:")
        print("   - ORGANIZATION_ID")
        print("   - BASE_URL")
        print("   - DANTA_API_KEY")
        print("\nPlease set these before running the script.")
        exit(1)

    print("Starting DantaLabs Maestro SDK Demo")
    print("=" * 50)

    main()

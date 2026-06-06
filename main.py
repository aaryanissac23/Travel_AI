import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import TypedDict, List, Optional
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END

# The common state of the graph is defined contaning all the info that the nodes may require at any point and it will be updated by each node.

class TravelState(TypedDict):
    country: str
    budget: float
    flights: List[dict]
    hotels: List[dict]
    selected_flight: Optional[dict]
    selected_hotel: Optional[dict]
    iteration_count: int
    critique_reason: Optional[str]
    critique_passed: bool

def validate_inputs(country: str, budget: float):
    if not country or not country.strip():
        raise ValueError("Validation Error: Country cannot be empty.")
    if budget < 0:
        raise ValueError("Validation Error: Budget cannot be negative.")

def load_travel_data() -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(base_dir, "travel_data.json")
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Data file not found at: {data_path}")
    with open(data_path, "r") as f:
        return json.load(f)

# Now after the state is defined , the data is fetched from travel.json.

async def fetch_flights(country: str, iteration: int) -> List[dict]:
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}]   -> [fetch_flights] Fetching flights...")
    await asyncio.sleep(1.0)
    
    flights = []
    for f in load_travel_data().get("flights", []):
        if f.get("country", "").lower() != country.lower():
            continue
        flights.append({"name": f["name"], "price": f["price"]})
    return flights

async def fetch_hotels(country: str, iteration: int) -> List[dict]:
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}]   -> [fetch_hotels] Fetching hotels...")
    await asyncio.sleep(1.0)
    
    hotels = []
    for h in load_travel_data().get("hotels", []):
        if h.get("country", "").lower() != country.lower():
            continue
        hotels.append({"name": h["name"], "price": h["price"]})
    return hotels

#Defining the nodes of the Graph

async def country_lock_node(state: TravelState) -> dict:
    validate_inputs(state["country"], state["budget"])
    print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [country_lock_node] Locked country {state['country']} (Iteration {state['iteration_count']})")
    return {}

async def flight_scout_node(state: TravelState) -> dict:
    start = time.time()
    flights = await fetch_flights(state["country"], state["iteration_count"])
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [flight_scout_node] Fetch took {time.time() - start:.3f} seconds.")
    return {"flights": flights}

async def hotel_matcher_node(state: TravelState) -> dict:
    start = time.time()
    hotels = await fetch_hotels(state["country"], state["iteration_count"])
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [hotel_matcher_node] Fetch took {time.time() - start:.3f} seconds.")
    return {"hotels": hotels}

def itinerary_aggregator_node(state: TravelState) -> dict:
    flights = state.get("flights", [])
    hotels = state.get("hotels", [])
    if not flights or not hotels:
        raise ValueError("Validation Error: Missing flights or hotels.")
        
    # Sort descending to propose premium options first, then systematically downgrade
    sorted_flights = sorted(flights, key=lambda x: x["price"], reverse=True)
    sorted_hotels = sorted(hotels, key=lambda x: x["price"], reverse=True)
    
    iteration = state.get("iteration_count", 0)
    max_iters = 5  # Spanning 6 total iterations (0 through 5)
    
    f_idx = min(int((iteration / max_iters) * (len(sorted_flights) - 1)), len(sorted_flights) - 1)
    h_idx = min(int((iteration / max_iters) * (len(sorted_hotels) - 1)), len(sorted_hotels) - 1)
    
    flight = sorted_flights[f_idx]
    hotel = sorted_hotels[h_idx]
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [itinerary_aggregator_node] Selected options for iteration {iteration}:")
    print(f"   Flight: {flight['name']} (${flight['price']}) | Hotel: {hotel['name']} (${hotel['price']})")
    return {"selected_flight": flight, "selected_hotel": hotel}

# Critique node using Groq structured output
class CritiqueResult(BaseModel):
    is_within_budget: bool = Field(description="True if flight price + hotel price <= maximum budget")
    total_cost: float = Field(description="The exact total cost of flight and hotel combined")
    reason: str = Field(description="Audit explanation comparing total cost with maximum budget")

async def critique_node(state: TravelState) -> dict:
    flight, hotel = state["selected_flight"], state["selected_hotel"]
    budget = state["budget"]
    
    llm = ChatGroq(model="llama-3.3-70b-versatile", max_retries=0, temperature=0.0)
    structured_llm = llm.with_structured_output(CritiqueResult)
    
    prompt = (
        f"Audit this package: Budget: ${budget:.2f}. "
        f"Flight: {flight['name']} (${flight['price']:.2f}). Hotel: {hotel['name']} (${hotel['price']:.2f}). "
        f"Does the total cost exceed the budget limit?"
    )
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [critique_node] Calling Groq structured output API...")
    
    # Retry with exponential backoff for transient 429 rate-limit errors
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            critique: CritiqueResult = await structured_llm.ainvoke(prompt)
            break
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < max_retries:
                wait = min(10 * (2 ** attempt), 60)
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [critique_node] Rate limited (429). Retrying in {wait}s... (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait)
            else:
                raise
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [critique_node] Result: Total: ${critique.total_cost:.2f} | Fits: {critique.is_within_budget}")
    
    return {
        "critique_reason": critique.reason if not critique.is_within_budget else None,
        "critique_passed": critique.is_within_budget
    }

def self_correct_node(state: TravelState) -> dict:
    iteration = state.get("iteration_count", 0)
    if iteration >= 6:
        raise RuntimeError(
            f"BudgetNotReachableError: Cannot resolve itinerary within budget limit of ${state['budget']:.2f}.\n"
            f"Last critique: {state['critique_reason']}"
        )
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [self_correct_node] Correction loop triggered. Iteration: {iteration} -> {iteration + 1}")
    return {"iteration_count": iteration + 1}

#Constructing the graph

def build_travel_graph() -> StateGraph:
    workflow = StateGraph(TravelState)
    workflow.add_node("country_lock", country_lock_node)
    workflow.add_node("flight_scout", flight_scout_node)
    workflow.add_node("hotel_matcher", hotel_matcher_node)
    workflow.add_node("itinerary_aggregator", itinerary_aggregator_node)
    workflow.add_node("critique", critique_node)
    workflow.add_node("correct", self_correct_node)
    
    workflow.add_edge(START, "country_lock")
    workflow.add_edge("country_lock", "flight_scout")
    workflow.add_edge("country_lock", "hotel_matcher")
    workflow.add_edge("flight_scout", "itinerary_aggregator")
    workflow.add_edge("hotel_matcher", "itinerary_aggregator")
    workflow.add_edge("itinerary_aggregator", "critique")
    workflow.add_conditional_edges("critique", lambda s: END if s["critique_passed"] else "correct")
    workflow.add_edge("correct", "country_lock")
    
    graph = workflow.compile()
    
    # Print the ASCII visualization of the graph flow
    try:
        print("\n" + "="*40 + "\nLangGraph Flow Topology:\n" + "="*40)
        graph.get_graph().print_ascii()
        print("="*40 + "\n")
    except Exception as e:
        print(f"Could not render ASCII graph: {e}")
        
    return graph

async def run_planner(country: str, budget: float):
    graph = build_travel_graph()
    initial_state = {
        "country": country, "budget": budget,
        "flights": [], "hotels": [], "selected_flight": None, "selected_hotel": None,
        "iteration_count": 0, "critique_reason": None, "critique_passed": False
    }
    
    print("\n" + "="*40 + f"\nPlanning trip to {country} | Budget: ${budget:.2f}\n" + "="*40)
    try:
        result = await graph.ainvoke(initial_state)
    except RuntimeError as e:
        print("="*40 + f"\n❌ Budget is not justifiable!\n{e}\n" + "="*40)
        return None
        
    print("="*40 + f"\nFinal Itinerary: {result['selected_flight']['name']} (${result['selected_flight']['price']}) & "
          f"{result['selected_hotel']['name']} (${result['selected_hotel']['price']})\n"
          f"Total: ${result['selected_flight']['price'] + result['selected_hotel']['price']:.2f} (Iterations: {result['iteration_count']})\n" + "="*40)
    return result

# ==========================================
# 5. Env Loading & Interactive CLI
# ==========================================

def load_env_file():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().strip("'\"")

async def main():
    load_env_file()
    while True:
        print("\n=== Travel Planner Menu ===")
        print("1. Run Success Demo (Japan, Budget $800)")
        print("2. Run Self-Correction Demo (Japan, Budget $150)")
        print("3. Run Failure Demo (Japan, Budget $80)")
        print("4. Custom Input")
        print("5. Exit")
        
        choice = input("Choice (1-5): ").strip()
        if choice == "1":
            await run_planner("Japan", 800.0)
        elif choice == "2":
            await run_planner("Japan", 150.0)
        elif choice == "3":
            await run_planner("Japan", 80.0)
        elif choice == "4":
            c = input("Enter country: ").strip()
            budget = float(input("Enter budget: ").strip())
            await run_planner(c, budget)
        elif choice == "5":
            break

if __name__ == "__main__":
    load_env_file()
    if len(sys.argv) > 2:
        asyncio.run(run_planner(sys.argv[1], float(sys.argv[2])))
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\nExiting.")

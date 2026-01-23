import timeit
import uuid
from datetime import datetime, timezone
from typing import List
from pydantic import BaseModel, Field, ConfigDict

# Mock Model
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Generate Data
COUNT = 1000
now = datetime.now(timezone.utc)
iso_now = now.isoformat()

data_strings = [
    {
        "id": str(uuid.uuid4()),
        "client_name": f"client_{i}",
        "timestamp": iso_now
    }
    for i in range(COUNT)
]

data_native = [
    {
        "id": str(uuid.uuid4()),
        "client_name": f"client_{i}",
        "timestamp": now
    }
    for i in range(COUNT)
]

# Functions to benchmark

def case_a_current():
    # Simulate DB return (copy to avoid mutation affecting other runs)
    items = [d.copy() for d in data_strings]

    # Inefficient Loop
    for check in items:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])

    # Validation
    return [StatusCheck(**item) for item in items]

def case_b_pydantic_parsing():
    # Simulate DB return
    items = [d.copy() for d in data_strings]

    # No loop, let Pydantic parse
    return [StatusCheck(**item) for item in items]

def case_c_native():
    # Simulate DB return (already datetimes)
    items = [d.copy() for d in data_native]

    # No loop, validation only
    return [StatusCheck(**item) for item in items]

if __name__ == "__main__":
    iterations = 100

    print(f"Benchmarking with {COUNT} items over {iterations} iterations...")

    t_a = timeit.timeit(case_a_current, number=iterations)
    print(f"Case A (Current - Manual Loop + Validation): {t_a:.4f}s")

    t_b = timeit.timeit(case_b_pydantic_parsing, number=iterations)
    print(f"Case B (Pydantic Parsing Only):              {t_b:.4f}s")

    t_c = timeit.timeit(case_c_native, number=iterations)
    print(f"Case C (Native Datetime - Optimized):        {t_c:.4f}s")

    improvement_a_c = (t_a - t_c) / t_a * 100
    print(f"\nImprovement (C vs A): {improvement_a_c:.1f}% faster")

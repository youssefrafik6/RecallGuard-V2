"""Read local CSV batches using the shared serving contract."""

from typing import BinaryIO

import pandas as pd

from recallguard.inference import BatchRequest, IncidentRequest


def read_batch(source: BinaryIO) -> BatchRequest:
    frame = pd.read_csv(source, dtype=str, keep_default_na=False, nrows=101)
    unknown = set(frame.columns) - IncidentRequest.model_fields.keys()
    if unknown:
        raise ValueError(
            f"Unsupported or duplicate columns: {', '.join(sorted(unknown))}"
        )
    return BatchRequest(incidents=frame.to_dict("records"))

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_PROPORTION = {"A": 0.25, "T": 0.25, "C": 0.25, "G": 0.25}

@dataclass
class Repeat:
    likelihood: float
    pattern: str
    pattern_max_reps: int
    pattern_min_reps: int

@dataclass
class Insert:
    total: int
    min_split: int
    max_split: int
    ave_gap: float
    sd_gap: float
    mutation_rate: float
    sequence: str

@dataclass
class SeqData:
    base_id: str
    generate: int
    max_len: int
    min_len: int
    proportion: Dict[str, float]
    repeats: List[Repeat]
    inserts: List[Insert]

BaseDict = Dict[str, SeqData]

class Data(BaseDict):
    def __init__(self, id_padding: int, seq_wrap: int, seed : bool|int = False):
        self.id_padding = id_padding
        self.seq_wrap = seq_wrap
        self.seed = seed

    def add_seqdata(self, seqdata: SeqData)-> None:
        """Adds the seqdata to de Data keys by base_id."""
        self[seqdata.base_id] = seqdata

    def get_default_proportion(self)-> Dict[str, float]:
        return DEFAULT_PROPORTION
    
    def get_proportion(self, base_id: str)-> Dict[str, float]:
        """Return the proportion of under base_id, or default proportion
        if None."""
        return self[base_id].proportion

class DataLoader:
    def __init__(self, config_json: str | Dict)-> None:
        """Loads the JSON into the class `Data`."""
        self._config_path = config_json
        self._config_dict = self._load_config_json()
        self._default_proportion = DEFAULT_PROPORTION

    def get_data(self)-> Data:
        """Return an instance of `Data` loaded with the JSON config data."""
        try:
            seed = self._config_dict["seed"]
        except KeyError:
            seed = False
        result = Data(
            id_padding = self._config_dict["id_padding"],
            seq_wrap = self._config_dict["seq_wrap"],
            seed = seed
        )
        for seqdata in self._get_seqdata_list_from_dict():
            result.add_seqdata(seqdata)
        return result

    def _load_config_json(self)-> Dict[str, Any]:
        """Load JSON file into dict."""
        if type(self._config_path) == dict:
            return self._config_path
        if type(self._config_path) == str:
            p = Path(self._config_path)
            with p.open('r', encoding='utf-8') as f:
                return json.load(f)
        else:
            raise TypeError(f"Only the config path or a dictionary can be used, not: {self._config_path}.")
        
    def _get_seqdata_list_from_dict(self)-> List[SeqData]:
        """Return a list with the Seqdata from the config_json."""
        result = []
        for seq_dict in self._config_dict["sequences"]:
            result.append(
                SeqData(
                    base_id = seq_dict["base_id"],
                    generate = seq_dict["generate"],
                    max_len = seq_dict["max_len"],
                    min_len = seq_dict["min_len"],
                    proportion = self._get_proportion_from_dict(seq_dict),
                    repeats = self._get_repeat_list_from_dict(seq_dict),
                    inserts = self._get_insert_list_from_dic(seq_dict)
                )
            )
        return result

    def _get_repeat_list_from_dict(self, seq_dict: dict)-> List[Repeat]:
        """Return a list of Repeats from a sequences dictionary."""
        repeats: list = seq_dict["repeats"]
        if repeats == []:
            return []
        return [Repeat(**rep) for rep in repeats]
        
    def _get_insert_list_from_dic(self, seq_dict: dict)-> List[Insert]:
        """Return a list with Insert dataclasses from an sequence dictionary."""
        inserts: List[Dict] = seq_dict["inserts"]
        if inserts == []:
            return []
        return [Insert(**ins) for ins in inserts]
    
    def _get_proportion_from_dict(self, seq_dict: dict)-> Dict[str, float]:
        if "proportion" not in seq_dict.keys():
            return self._default_proportion
        return seq_dict["proportion"]

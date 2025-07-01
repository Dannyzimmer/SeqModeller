import click
from libs.DataLoader.data_loader import DataLoader, SeqData, Repeat, Insert, BaseDict
from typing import List, Iterator, Dict, Tuple
from abc import abstractmethod
from dataclasses import dataclass
import random
import math
from collections import Counter
from itertools import repeat
from datetime import datetime
from statistics import fmean, stdev

@dataclass
class SeqGenParts:
    base_id: str
    repeats: List[str]
    inserts: List[str]
    nucleotides: List[str]
    inserts_gaps: Dict[str, int]
    mutations: Dict[str, int]

SeqGenDict = Dict[str, SeqGenParts]

class DataGen(SeqGenDict):
    def __init__(self):
        """Class to store the generated data."""
        super().__init__()

    def add_seqgen(self, seqgen: SeqGenParts)-> None:
        """Adds the seqdata to de Data keys by base_id."""
        self[seqgen.base_id] = seqgen

@dataclass
class SeqGenReport:
    base_id: str
    inserts_counts: Dict[str, int]
    repeats_counts: Dict[str, int]
    nuc_proportion: Dict[str, float]
    sequence_num: int
    inserts_gaps: Dict[str, int]
    mutations_num: Dict[str, int]
    ave_len: float
    sd_len: float

ReportDic = Dict[str, SeqGenReport]
GenResult = List[str]

class DataGenReport(ReportDic):
    def __init__(self, seed):
        super().__init__()
        self.seed = seed

    def add_seqreport(self, seqreport: SeqGenReport):
        self[seqreport.base_id] = seqreport

class Generator:
    def __init__(self, config_json: str|Dict, seed = None):
        self.data = DataLoader(config_json).get_data()
        self.seed = self._init_seed(seed)
        self.rd = random.Random(self.seed)
        self.datagen = DataGen()
        self.repeat_gen = RepeatsGenerator(self)
        self.insert_gen = InsertsGenerator(self)
        self.nucleotide_gen = NucleotidesGenerator(self)
        self.sequence_gen = SequenceGenerator(self)

    def _init_seed(self, seed: int|None)-> int:
        """Return the seed to use from the input seed of the class. Requires
        attribute `self.data` to be available.
        """
        if seed != None and seed != False:
            return seed
        if self.data.seed != False:
            return self.data.seed
        return self._get_random_seed()

    def _get_random_seed(self)-> int:
        random_int = random.randrange(50, 10000000)
        seed = list(str(datetime.now().timestamp()).replace('.', ''))
        random.shuffle(seed)
        return int(''.join(seed)) + random_int

    def _fill_datagen(self)-> None:
        for base_id in self.data.keys():
            inserts = []
            for report_dic, insert in self.insert_gen.generate(base_id):
                inserts.append(insert)
            generation = list(self.insert_gen.generate(base_id))
            self.datagen.add_seqgen(
                SeqGenParts(
                    base_id = base_id,
                    repeats = self.repeat_gen.generate(base_id),
                    inserts = [i[1] for i in generation],
                    nucleotides = self.nucleotide_gen.generate(base_id),
                    inserts_gaps = {i[1]: i[0]["n_gaps"] for i in generation},
                    mutations = {i[1]: i[0]["n_mutations"] for i in generation}
                )
            )
    
    def _yield_sequences(self)-> Iterator[str]:
        self._fill_datagen()
        for base_id in self.datagen.keys():
            yield self.sequence_gen.generate(base_id)

    def generate_fasta(self, report = False)-> Tuple[SeqGenReport, GenResult]:
        """Return a tuple with the DataGenReport and the generated FASTA 
        as a list of sequences (header\nsequence).
        :return: Tuple[SeqGenReport, GenResult]
        """
        self._fill_datagen()
        fasta_content = []
        data_gen_report = DataGenReport(self.seed)
        for base_id in self.datagen.keys():
            report, sequences = self.sequence_gen.generate(base_id)
            data_gen_report.add_seqreport(report)
            for i, sequence in enumerate(sequences):
                seq_count = i + 1
                id = HeaderTools.generate_seq_id(
                    base_id = base_id,
                    seq_count = seq_count,
                    padding = self.data.id_padding
                )
                header = HeaderTools.generate_header(
                    sequence_id = id,
                    sequence = sequence
                )
                wrapped_seq = HeaderTools.wrap_text(
                    text = sequence,
                    width = self.data.seq_wrap
                )
                fasta_content.append(f'{header}\n{wrapped_seq}')
        return (data_gen_report, fasta_content)
    
    def get_generated_fasta(self)-> Tuple[List[str], List[str]]:
        """Return the generated FASTA and the report generation by sequence.
                Return: (report, fasta_lines)
        """
        report, seq = self.generate_fasta()
        return (ReportMaker.get_report_print(report), seq)

class BaseGenerator:
    def __init__(self, generator: Generator):
        self.generator = generator

    @abstractmethod
    def generate(self, base_id: str)-> List[str]:
        pass

class RepeatsGenerator(BaseGenerator):
    def generate(self, base_id: str)-> Iterator[str]:
        """Yield generated repeat sequences under `base_id`. Applies the
        likelihood of a repetition per generated sequence.
        """
        for rep in self.generator.data[base_id].repeats:
            for _ in range(self.generator.data[base_id].generate):
                if self.generator.rd.random() > rep.likelihood:
                    continue
                yield self._generate_single_rep(rep)

    def _generate_single_rep(self, repeat: Repeat)-> str:
        """Generates a repeat sequence from a Repeat dataclass."""
        pat = repeat.pattern
        rmax = repeat.pattern_max_reps
        rmin = repeat.pattern_min_reps
        return ''.join([pat for r in range(self.generator.rd.randint(rmin, rmax))])

class InsertsGenerator(BaseGenerator):
    def generate(self, base_id: str)-> Iterator[str]:
        """Yield generated insert sequences under `base_id`."""
        for ins in self.generator.data[base_id].inserts:
            for i in range(ins.total):
                yield self._generate_single_ins(ins, base_id)

    def _split_insert(self, insert: Insert)-> List[str]:
        """Return a list with the splitted sequences of the insert."""
        s = insert.sequence
        n_splits = self.generator.rd.randint(insert.min_split, insert.max_split)
        split_at = self.generator.rd.sample(range(1, len(insert.sequence) - 1), n_splits)
        ps = sorted(set(split_at))
        indices = [0] + ps + [len(s)]
        return [s[i:j] for i, j in zip(indices, indices[1:])]
    
    def _mutate_seq(
            self, sequence: str, mutation_rate: float, proportion: dict
        )-> Tuple[Dict[str, int], str]:
        """Mutates the given sequence following the given proportion at the
        given mutation rate. The mutation_rate is applied per nucleotide.
        Return a tuple: 
            (
                {"n_mutations": mutation_num}, 
                mutated_sequence
            ).
        """
        if mutation_rate >= 1:
            raise ValueError(f"[ERROR]: Mutation rate must be lower than 1 (now is: {mutation_rate})")
        if mutation_rate == 0:
            return ({"n_mutations": 0}, sequence)
        nuc = [k for k in proportion.keys()]
        weights = [int(100 - (100 - (w*100))) for w in proportion.values()]
        mutated_seq = list(sequence)
        mutation_num = 0
        for position in range(len(mutated_seq)):
            if self.generator.rd.random() < mutation_rate:
                mutated_seq[position] = self.generator.rd.choices(nuc, weights=weights, k=1)[0]
                mutation_num += 1
        return ({"n_mutations": mutation_num}, ''.join(mutated_seq))

    def _generate_single_ins(self, insert: Insert, base_id: str)-> Tuple[int, str]:
        """Generates the insert sequence from an Insert dataclass. Return a tuple
        with the number of gaps and the resulting insert sequence.

        (
            {"n_mutations": int, "n_gaps": int},
            insert_sequence
        )
        """
        proportion = self.generator.data.get_proportion(base_id)
        insert_segments = self._split_insert(insert)
        ngaps = len(insert_segments) - 1
        gap_lengths = [math.ceil(self.generator.rd.normalvariate(insert.ave_gap, insert.sd_gap)) for i in range(ngaps)]
        nuc = [k for k in proportion.keys()]
        weights = [int(100 - (100 - (w*100))) for w in proportion.values()]
        gaps = [''.join(self.generator.rd.choices(nuc, weights=weights, k=i)) for i in gap_lengths]
        result = []
        for i, ins in enumerate(insert_segments):
            result.append(ins)
            if i < len(gaps):
                result.append(gaps[i])
        sequence = ''.join(result)
        report_dic, mutated_seq = self._mutate_seq(sequence, insert.mutation_rate, proportion)
        report_dic["n_gaps"] = len(insert_segments) - 1
        return (report_dic, mutated_seq)

class NucleotidesGenerator(BaseGenerator):
    def generate(self, base_id: str)-> Iterator[str]:
        """Yield generated nucleotides sequences under `base_id`."""
        seqdata = self.generator.data[base_id]
        for i in range(seqdata.generate):
            yield self._generate_single_seq(seqdata)

    def _generate_single_seq(self, seqdata: SeqData)-> str:
        """Generates a nucleotide sequence from a SeqData dataclass."""
        nuc = [k for k in seqdata.proportion.keys()]
        weights = [int(100 - (100 - (w*100))) for w in seqdata.proportion.values()]
        length = self.generator.rd.randint(seqdata.min_len, seqdata.max_len)
        return ''.join(self.generator.rd.choices(nuc, weights=weights, k=length))
    
class SequenceGenerator(BaseGenerator):
    def generate(self, base_id: str)-> Tuple[SeqGenReport, GenResult]:
        """Return a tuple with the report and the generated final sequences
        under `base_id`.
        """
        seqgen = self.generator.datagen[base_id]
        return self._generate_sequences(seqgen)
    
    def _insert_strs_in_seq(
            self, insert_this: List[str], into_this: str)-> str:
        """Insert strings from `insert_this` into the string `into_this` at
        random positions, but following `insert_this` items order. 
        If `into_this` is an empty string, returns `insert_this` as a single
        string.

        :param List[str] insert_this: List with the strings to insert.
        :param str into_this: String where each item of `insert_this` will be
        inserted.
        :return: A single string containing all items in `insert_this` 
        sequencially inserted at pseudo-random position.
        """
        if into_this == "":
            return ''.join(insert_this)
        seq_list = list(into_this)
        seq_idx = range(0, len(seq_list))
        insert_positions = self.generator.rd.choices(seq_idx, k = len(insert_this))
        for i, into_this in zip(insert_positions, insert_this):
            seq_list.insert(i, into_this)
        return ''.join(seq_list)

    def _sample_items_on_iterable(self, items: List[str], total: list)-> List:
        """Sample items in total. Return all the items if total == 1. Return
        an empty list if items is empty.
        """
        item_len = len(items)
        total_len = len(total)
        if total_len == 1:
            pick_n = item_len
        elif item_len > 0:
            pick_n = self.generator.rd.randint(0, item_len)
        else:
            return []
        return self.generator.rd.sample(items, k = pick_n)

    def _generate_sequences(
            self, seqgen: SeqGenParts
        )-> Tuple[SeqGenReport, GenResult]:
        """Return a tuple with the nucleotide sequences from a SeqGenParts
        dataclass and a SeqGenReport objet."""
        repeats = list(seqgen.repeats)
        inserts = list(seqgen.inserts)
        raw_seqs = list(seqgen.nucleotides)
        insertions = repeats + inserts
        sequences = []
        for raw_seq in raw_seqs:
            adds = self._sample_items_on_iterable(insertions, raw_seqs)
            sequences.append(self._insert_strs_in_seq(adds, raw_seq))
            for add in adds:
                insertions.remove(add)
        report = ReportMaker.get_seq_gen_report(
            base_id = seqgen.base_id,
            inserts = inserts,
            repeats = repeats,
            sequences = sequences,
            inserts_gaps = seqgen.inserts_gaps,
            mutations_num = seqgen.mutations
        )
        return (report, sequences)
    
class ReportMaker:
    @staticmethod
    def get_seq_gen_report(
            base_id: str, inserts: GenResult, 
            repeats: GenResult, sequences: GenResult, 
            inserts_gaps: Dict[str, int], mutations_num: Dict[str, int]
        )-> SeqGenReport:
        """Creates a SeqGenReport object."""
        nuc_count = Counter(''.join(sequences))
        nuc_total = nuc_count.total()
        nuc_prop = {i: round(nuc_count[i]/nuc_total, 2) for i in nuc_count.keys()}
        len_seqs = len(sequences)
        if len(sequences) > 1:
            ave_len = fmean(map(len, sequences))
            sd_len = stdev(map(len, sequences))
        else:
            ave_len = len(sequences)
            sd_len = 0

        return SeqGenReport(
            base_id = base_id,
            inserts_counts = dict(Counter(inserts)),
            repeats_counts = dict(Counter(repeats)),
            nuc_proportion = nuc_prop,
            sequence_num = len(sequences),
            inserts_gaps = inserts_gaps,
            mutations_num = mutations_num,
            ave_len = ave_len,
            sd_len = sd_len
        )
    
    @staticmethod
    def indent(text: str, n: int = 1):
        indentation = ''.join(list(repeat('\t', n)))
        return f'{indentation}{text}'
    
    @classmethod
    def get_report_print(cls, data_report: DataGenReport)-> List[str]:
        """Converts a DataGenReport instance into a list ready for print."""
        result = [f'SEED\n{cls.indent(data_report.seed)}']
        for base_id in data_report.keys():
            report = data_report[base_id]
            result.append(f'BATCH')
            line = []
            result.append(cls.indent(f'n\tid\tA\tT\tC\tG\tave_len\tsd_len'))
            line.append(cls.indent(f"{report.sequence_num}\t{base_id}\t"))
            # Nucleotide proportion
            for nuc in ["A","T","C","G"]:
                prop = report.nuc_proportion[nuc]
                line.append(f'{prop}\t')
            line.append(f'{round(report.ave_len, 2)}\t{round(report.sd_len, 2)}')
            result.append(''.join(line))

            # Inserts
            result.append('INSERTS')
            result.append(cls.indent(f'n\tlen\tmut\tgaps\tsequence'))
            for seq, n in data_report[base_id].inserts_counts.items():
                length = len(seq)
                mutations = data_report[base_id].mutations_num[seq]
                gaps = data_report[base_id].inserts_gaps[seq]
                result.append(cls.indent(f'{n}\t{length}\t{mutations}\t{gaps}\t{seq}'))
            # Repeats
            result.append('REPEATS')
            result.append(cls.indent(f'n\tlen\tsequence'))
            for seq, n in data_report[base_id].repeats_counts.items():
                length = len(seq)
                result.append(cls.indent(f'{n}\t{length}\t{seq}'))
        return result

class HeaderTools:
    @staticmethod
    def _pad_num(num: int, n: int = 4)-> str:
        """Pads right the given number with `n` leading zeros."""
        return str(num).rjust(n, "0")

    @staticmethod    
    def wrap_text(text: str, width: int | bool) -> str:
        """Wrap the given text at the given width."""
        if width == False:
            return text
        return "\n".join(text[i:i+width] for i in range(0, len(text), width))
    
    @classmethod 
    def generate_seq_id(
        cls, base_id: str, seq_count: int, padding: int = 4)-> str:
        """Return the header of the sequence."""
        return f'{base_id}{cls._pad_num(seq_count, padding)}'
    
    @staticmethod 
    def generate_header(sequence_id: str, sequence: str)-> str:
        """Return the header of the sequence."""
        return f'>{sequence_id} [length={len(sequence)}]'

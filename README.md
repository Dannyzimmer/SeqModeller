# sequenceModeller

A powerful GUI application for generating synthetic DNA sequences with customizable patterns, insertions, and repeats. Perfect for bioinformatics research, testing sequence analysis tools, and creating controlled datasets.

<img src="images/screenshot.png" alt="sequenceModeller Interface" width="700"/>

## Features

- **Intuitive GUI**: Easy-to-use interface built with PyQt6
- **Flexible Sequence Generation**: Configure nucleotide proportions, sequence lengths, and generation counts
- **Pattern Repeats**: Add repeating patterns with customizable likelihood and repetition ranges
- **Sequence Insertions**: Insert specific sequences with mutation rates and split configurations
- **Batch Processing**: Generate multiple sequence batches with different parameters
- **Multiple Output Formats**: Generate FASTA files, detailed reports, and JSON configurations
- **Session Management**: Recent files with persistent output path associations
- **Import/Export**: Save and load configurations for reproducible results

## Requirements

- Python 3.8+
- PyQt6

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/sequenceModeller.git
cd sequenceModeller
```

2. Install dependencies:
```bash
pip install PyQt6
```

3. Run the application:
```bash
python main.py
```

## Quick Start

1. **Configure General Settings**: Set ID padding, sequence wrapping, and nucleotide proportions
2. **Add Sequence Batches**: Click "Add" to create new sequence batches with unique Base IDs
3. **Configure Generation**: Set the number of sequences, min/max lengths for each batch
4. **Add Patterns** (optional): Define repeating patterns with likelihood and repetition ranges
5. **Add Insertions** (optional): Insert specific sequences with mutation and split parameters
6. **Set Output Files**: Choose where to save your FASTA, report, and configuration files
7. **Generate**: Click "Generate" to create your synthetic sequences

## Configuration Structure

sequenceModeller uses JSON configuration files with the following structure:

```json
{
    "id_padding": 4,
    "seq_wrap": 70,
    "seed": 12345,
    "sequences": [
        {
            "base_id": "TEST",
            "generate": 10,
            "max_len": 1000,
            "min_len": 500,
            "proportion": {"A": 0.25, "T": 0.25, "C": 0.25, "G": 0.25},
            "repeats": [
                {
                    "likelihood": 0.5,
                    "pattern": "ATCG",
                    "pattern_max_reps": 50,
                    "pattern_min_reps": 10
                }
            ],
            "inserts": [
                {
                    "total": 4,
                    "max_split": 2,
                    "min_split": 0,
                    "ave_gap": 100,
                    "sd_gap": 20,
                    "mutation_rate": 0.05,
                    "sequence": "ATCGATCGATCG"
                }
            ]
        }
    ]
}
```

## Output Files

- **FASTA**: Standard FASTA format with generated sequences
- **Report**: Detailed generation statistics and parameters
- **Config JSON**: Complete configuration for reproducibility

## Advanced Features

### Pattern Repeats
- Define custom DNA patterns that repeat throughout sequences
- Set likelihood of occurrence and min/max repetition counts
- Useful for simulating microsatellites or tandem repeats

### Sequence Insertions
- Insert specific sequences at random positions
- Configure mutation rates for realistic variation
- Control sequence splitting and gap distribution
- Perfect for simulating known motifs or regulatory elements

### Session Management
- Recent files menu with automatic path association
- Persistent settings across application sessions
- Easy project switching and configuration reuse

## File Structure

```
sequenceModeller/
├── main.py                 # Application entry point
├── GUI/
│   ├── app.ui             # Main interface definition
│   └── ...                # Additional UI files
├── libs/
│   └── Generator/         # Sequence generation engine
├── images/                # Screenshots and documentation images
└── README.md
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions, bug reports, or feature requests, please open an issue on GitHub.
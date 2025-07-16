import sys
import os
import json
from pathlib import Path
from PyQt6 import QtWidgets, QtCore, QtGui, uic
from PyQt6.QtWidgets import (QApplication, QMainWindow, QMessageBox, 
                            QFileDialog, QTableWidgetItem,
                            QDialog, QPlainTextEdit, QVBoxLayout, QPushButton,
                            QLabel)
from PyQt6.QtCore import Qt, QStringListModel
from GUI.app_ui import Ui_MainWindow
from GUI.about_ui import Ui_Form
import resources_rc

BIN_PATH = os.path.dirname(sys.argv[0])
SESSION_FILE = os.path.join(BIN_PATH, ".sm_session.json")

def get_path_to_ui(ui_filename):
    """Return the full path to the given ui file"""
    rel_ui_dir = "GUI"
    try:
        base_path = Path(__file__).parent
    except Exception:
        base_path = Path(sys.argv[0]).parent
    return base_path / rel_ui_dir / ui_filename

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller/Nuitka"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        try:
            base_path = Path(__file__).parent
        except Exception:
            base_path = Path(sys.argv[0]).parent
    
    return base_path / relative_path

class InsertFormDialog(QDialog):
    """Dialog for inserting sequences more comfortably"""
    def __init__(self, initial_text="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insert Sequence")
        self.setModal(True)
        self.resize(500, 300)
        
        layout = QVBoxLayout()
        
        label = QLabel("Insert sequence (line breaks will be removed):")
        layout.addWidget(label)
        
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(initial_text)
        layout.addWidget(self.text_edit)
        
        button_layout = QtWidgets.QHBoxLayout()
        self.accept_button = QPushButton("Accept")
        self.cancel_button = QPushButton("Cancel")
        
        self.accept_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.accept_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def get_text(self):
        return self.text_edit.toPlainText().replace('\n', '').replace('\r', '')

class AboutDialog(QDialog, Ui_Form):
    """Simple About dialog"""
    def __init__(self, parent=None):
        super().__init__()
        self.setupUi(self)

class SeqModellerMainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        
        # Set window icon
        self.set_window_icon()
        
        # Variables to store data
        self.sequences_data = {}  # Dictionary to store data for each sequence
        self.current_sequence = None  # Currently selected sequence
        self.output_directory = None  # Default directory for output files
        self.current_config_file = None  # Currently imported config file path
        
        # Variables for recent files
        self.recent_files = []  # List of recent files with their data
        self.max_recent_files = 10  # Maximum number of recent files
        self.recent_files_actions = []  # List of recent file actions
        self.session_file = SESSION_FILE  # Session file
        
        # Variable to track if any configuration has been saved
        self.has_saved_config = False
        
        # Configure model for QListView
        self.sequence_model = QStringListModel()
        self.sequence_list.setModel(self.sequence_model)
        
        # Allow editing in QListView for renaming
        self.sequence_list.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked)
        
        # Configure interface
        self.setup_connections()
        self.setup_initial_state()
        self.load_recent_files()
        self.update_recent_files_menu()
        self.make_output_fields_editable()
    
    def set_window_icon(self):
        """Set the window icon"""
        try:
            # Try resource first
            icon = QtGui.QIcon(":/images/window_icon")
            self.setWindowIcon(icon)
        except Exception as e:
            print(f"Warning: Could not load window icon: {e}")
    
    def setup_ui_manually(self):
        """Manual UI setup if .ui file cannot be loaded"""
        self.setWindowTitle("fastaModeller")
        self.setMinimumSize(936, 764)
        
        # This is a basic implementation if the .ui file cannot be loaded
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QtWidgets.QVBoxLayout(central_widget)
        label = QLabel("Error: Could not load app.ui file")
        layout.addWidget(label)
    
    def setup_connections(self):
        """Configure all signal and slot connections"""
        try:
            # Main button connections
            self.btn_new_seq.clicked.connect(self.add_new_sequence)
            self.btn_rm_seq.clicked.connect(self.remove_sequence)
            self.btn_generate.clicked.connect(self.generate_files)
            
            # Output file connections
            self.pushButton_report.clicked.connect(lambda: self.select_output_file("report", "Text files (*.txt)"))
            self.pushButton_config_json.clicked.connect(lambda: self.select_output_file("config", "JSON files (*.json)"))
            self.pushButton_fasta.clicked.connect(lambda: self.select_output_file("fasta", "FASTA files (*.fasta *.fa)"))
            
            # Sequence list connections
            self.sequence_list.selectionModel().selectionChanged.connect(self.on_sequence_selection_changed)
            
            # Connection to handle sequence renaming
            self.sequence_model.dataChanged.connect(self.on_sequence_renamed)
            
            # Tab save button connections
            self.btn_random_generation_save.clicked.connect(self.save_random_generation_config)
            self.btn_insert_save.clicked.connect(self.save_insert_config)
            self.btn_rep_save.clicked.connect(self.save_repeat_config)
            
            # Insert and repeat table connections
            self.btn_new_insert.clicked.connect(self.add_new_insert)
            self.btn_rm_insert.clicked.connect(self.remove_insert)
            self.btn_new_repeat.clicked.connect(self.add_new_repeat)
            self.btn_rm_repeat.clicked.connect(self.remove_repeat)
            
            # Insert sequence dialog button connection
            self.btn_insert_open_sequence.clicked.connect(self.open_insert_sequence_dialog)
            
            # Table selection connections
            self.table_inserts.itemSelectionChanged.connect(self.on_insert_selection_changed)
            self.table_repeats.itemSelectionChanged.connect(self.on_repeat_selection_changed)
            
            # About menu connection
            self.actionAbout.triggered.connect(self.show_about_dialog)
            
            # Import Config menu connection
            self.actionImport_config.triggered.connect(self.import_config)
            
            # Recent Files menu connection
            self.actionRemove_recent_files.triggered.connect(self.clear_recent_files)
            
            # Connection to update max split when insert sequence changes
            self.lineEdit_insert_seq.textChanged.connect(self.update_insert_max_split_constraint)
            
            # Connection to enable/disable btn_new_seq based on base_id text
            self.lineEdit_base_id.textChanged.connect(self.update_new_seq_button_state)
            
            # Connections to validate proportion sum
            self.doubleSpinBox_A.valueChanged.connect(self.validate_proportion_sum)
            self.doubleSpinBox_T.valueChanged.connect(self.validate_proportion_sum)
            self.doubleSpinBox_C.valueChanged.connect(self.validate_proportion_sum)
            self.doubleSpinBox_G.valueChanged.connect(self.validate_proportion_sum)
            
            # Slider-spinbox connections (already in .ui but reinforcing them)
            self.setup_slider_spinbox_connections()
            
        except AttributeError as e:
            print(f"Warning: Could not connect some signals: {e}")
    
    def setup_slider_spinbox_connections(self):
        """Configure connections between sliders and spinboxes"""
        try:
            # Bidirectional connections between sliders and spinboxes
            slider_spinbox_pairs = [
                (self.horizontalSlider_generate, self.spinBox_generate),
                (self.horizontalSlider_max_len, self.spinBox_max_len),
                (self.horizontalSlider_min_len, self.spinBox_min_len),
                (self.horizontalSlider_insert_max_split, self.spinBox_insert_max_split),
                (self.horizontalSlider_insert_min_split, self.spinBox_insert_min_split),
                (self.horizontalSlider_insert_min_split_2, self.spinBox_insert_ave_gap),
                (self.horizontalSlider_insert_min_split_3, self.spinBox_insert_sd_gap),
                (self.horizontalSlider_max_reps, self.spinBox_max_reps),
                (self.horizontalSlider_min_reps, self.spinBox_min_reps),
            ]
            
            for slider, spinbox in slider_spinbox_pairs:
                slider.valueChanged.connect(spinbox.setValue)
                spinbox.valueChanged.connect(slider.setValue)
            
            # Configure minimum vs maximum value limitations
            self.setup_min_max_constraints()
        except AttributeError as e:
            print(f"Warning: Could not connect some signals: {e}")
                
    def make_output_fields_editable(self):
        """Make output fields editable"""
        try:
            self.lineEdit_report.setReadOnly(False)
            self.lineEdit_config_json.setReadOnly(False)
            self.lineEdit_fasta.setReadOnly(False)
        except AttributeError:
            pass
    
    def update_new_seq_button_state(self):
        """Enable/disable btn_new_seq based on base_id text"""
        try:
            has_text = bool(self.lineEdit_base_id.text().strip())
            self.btn_new_seq.setEnabled(has_text)
        except AttributeError:
            pass
    
    def update_generate_button_state(self):
        """Enable/disable btn_generate based on saved configuration state"""
        try:
            self.btn_generate.setEnabled(self.has_saved_config)
        except AttributeError:
            pass
    
    def validate_proportion_sum(self):
        """Validate that proportion values sum to 1 and update styling"""
        try:
            # Get current values
            a_val = self.doubleSpinBox_A.value()
            t_val = self.doubleSpinBox_T.value()
            c_val = self.doubleSpinBox_C.value()
            g_val = self.doubleSpinBox_G.value()
            
            total = a_val + t_val + c_val + g_val
            
            # Check if sum is approximately 1 (allowing small floating point errors)
            is_valid = abs(total - 1.0) < 0.001
            
            # Define styles
            normal_style = ""
            error_style = "QDoubleSpinBox { color: red; }"
            
            # Apply styles
            style = normal_style if is_valid else error_style
            self.doubleSpinBox_A.setStyleSheet(style)
            self.doubleSpinBox_T.setStyleSheet(style)
            self.doubleSpinBox_C.setStyleSheet(style)
            self.doubleSpinBox_G.setStyleSheet(style)
            
        except AttributeError:
            pass
    
    def check_proportion_sum_valid(self):
        """Check if proportion sum is valid (equals 1)"""
        try:
            a_val = self.doubleSpinBox_A.value()
            t_val = self.doubleSpinBox_T.value()
            c_val = self.doubleSpinBox_C.value()
            g_val = self.doubleSpinBox_G.value()
            
            total = a_val + t_val + c_val + g_val
            return abs(total - 1.0) < 0.001
        except AttributeError:
            return True  # Default to valid if we can't check
    
    def load_recent_files(self):
        """Load recent files list from session file"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                    self.recent_files = session_data.get('recent_files', [])
                    
                    # Filter files that no longer exist
                    self.recent_files = [
                        file_data for file_data in self.recent_files
                        if os.path.exists(file_data.get('config_path', ''))
                    ]
            else:
                self.recent_files = []
        except Exception:
            self.recent_files = []
    
    def save_recent_files(self):
        """Save recent files list to session file"""
        try:
            session_data = {
                'recent_files': self.recent_files
            }
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2)
        except Exception:
            pass
    
    def load_associated_paths(self, file_entry):
        """Load associated file paths from recent file entry"""
        try:
            # Load paths if they exist
            report_path = file_entry.get('report_path', '')
            fasta_path = file_entry.get('fasta_path', '')
            config_json_path = file_entry.get('config_json_path', '')
            
            if report_path:
                self.lineEdit_report.setText(report_path)
            if fasta_path:
                self.lineEdit_fasta.setText(fasta_path)
            if config_json_path:
                self.lineEdit_config_json.setText(config_json_path)
                
        except AttributeError:
            pass
    
    def add_to_recent_files(self, file_path):
        """Add file to recent files list"""
        try:
            file_path = os.path.abspath(file_path)
            
            # Create recent file entry with current paths
            file_entry = {
                'config_path': file_path,
                'report_path': getattr(self.lineEdit_report, 'text', lambda: '')(),
                'fasta_path': getattr(self.lineEdit_fasta, 'text', lambda: '')(),
                'config_json_path': getattr(self.lineEdit_config_json, 'text', lambda: '')(),
                'timestamp': QtCore.QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)
            }
            
            # Remove if already exists (compare only by config_path)
            self.recent_files = [
                f for f in self.recent_files 
                if f.get('config_path') != file_path
            ]
            
            # Add to beginning
            self.recent_files.insert(0, file_entry)
            
            # Keep only the latest files
            if len(self.recent_files) > self.max_recent_files:
                self.recent_files = self.recent_files[:self.max_recent_files]
            
            # Update menu
            self.update_recent_files_menu()
            
            # Save configuration
            self.save_recent_files()
            
        except Exception:
            pass
    
    def update_recent_files_menu(self):
        """Update recent files menu"""
        try:
            # Clear previous actions
            for action in self.recent_files_actions:
                self.menuRecent_files.removeAction(action)
            self.recent_files_actions.clear()
            
            # Add new actions
            for i, file_entry in enumerate(self.recent_files):
                file_path = file_entry.get('config_path', '')
                if os.path.exists(file_path):
                    file_name = os.path.basename(file_path)
                    action_text = f"{i+1}. {file_name}"
                    
                    action = QtGui.QAction(action_text, self)
                    action.setToolTip(file_path)
                    action.triggered.connect(lambda checked, entry=file_entry: self.open_recent_file(entry))
                    
                    # Insert before "Remove recent files" action
                    if hasattr(self, 'actionRemove_recent_files'):
                        self.menuRecent_files.insertAction(self.actionRemove_recent_files, action)
                    else:
                        self.menuRecent_files.addAction(action)
                    
                    self.recent_files_actions.append(action)
            
            # Add separator if there are recent files
            if self.recent_files_actions and hasattr(self, 'actionRemove_recent_files'):
                separator = self.menuRecent_files.insertSeparator(self.actionRemove_recent_files)
                self.recent_files_actions.append(separator)
            
            # Enable/disable menu depending on whether there are files
            if hasattr(self, 'menuRecent_files'):
                self.menuRecent_files.setEnabled(len(self.recent_files) > 0)
                
        except AttributeError:
            pass
    
    def open_recent_file(self, file_entry):
        """Open recent file with its associated paths"""
        try:
            file_path = file_entry.get('config_path', '')
            
            if not os.path.exists(file_path):
                QMessageBox.warning(
                    self, 
                    "File Not Found", 
                    f"The file '{file_path}' no longer exists."
                )
                # Remove from list
                if file_entry in self.recent_files:
                    self.recent_files.remove(file_entry)
                    self.update_recent_files_menu()
                    self.save_recent_files()
                return
            
            # Read and load the file
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except json.JSONDecodeError as e:
                QMessageBox.critical(
                    self, 
                    "Import Error", 
                    f"Invalid JSON file: {str(e)}"
                )
                return
            except Exception as e:
                QMessageBox.critical(
                    self, 
                    "Import Error", 
                    f"Error reading file: {str(e)}"
                )
                return
            
            # Validate structure
            if not self.validate_config_structure(config):
                QMessageBox.critical(
                    self, 
                    "Import Error", 
                    "Invalid configuration file structure"
                )
                return
            
            # Ask whether to replace current configuration
            if self.sequences_data:
                reply = QMessageBox.question(
                    self,
                    "Replace Configuration",
                    "This will replace the current configuration. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            # Load configuration
            self.load_config_into_gui(config)
            
            # Load associated file paths
            self.load_associated_paths(file_entry)
            
            # Update output directory
            self.output_directory = os.path.dirname(file_path)
            
            # Set current config file
            self.current_config_file = file_path
            
            # Move to front of recent list
            self.add_to_recent_files(file_path)
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error", 
                f"Unexpected error opening file: {str(e)}"
            )
    
    def clear_recent_files(self):
        """Clear recent files list"""
        try:
            reply = QMessageBox.question(
                self,
                "Clear Recent Files",
                "Are you sure you want to clear the recent files list?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.recent_files.clear()
                self.update_recent_files_menu()
                self.save_recent_files()
                
        except Exception:
            pass
    
    def setup_min_max_constraints(self):
        """Configure limitations between minimum and maximum values"""
        try:
            # Configure limitations for length (min_len vs max_len)
            self.horizontalSlider_max_len.valueChanged.connect(self.update_min_len_constraint)
            self.spinBox_max_len.valueChanged.connect(self.update_min_len_constraint)
            self.horizontalSlider_min_len.valueChanged.connect(self.validate_min_len_value)
            self.spinBox_min_len.valueChanged.connect(self.validate_min_len_value)
            
            # Configure limitations for insert split (min_split vs max_split)
            self.horizontalSlider_insert_max_split.valueChanged.connect(self.update_min_split_constraint)
            self.spinBox_insert_max_split.valueChanged.connect(self.update_min_split_constraint)
            self.horizontalSlider_insert_min_split.valueChanged.connect(self.validate_min_split_value)
            self.spinBox_insert_min_split.valueChanged.connect(self.validate_min_split_value)
            
            # Configure limitations for repeats (min_reps vs max_reps)
            self.horizontalSlider_max_reps.valueChanged.connect(self.update_min_reps_constraint)
            self.spinBox_max_reps.valueChanged.connect(self.update_min_reps_constraint)
            self.horizontalSlider_min_reps.valueChanged.connect(self.validate_min_reps_value)
            self.spinBox_min_reps.valueChanged.connect(self.validate_min_reps_value)
            
            # Initialize max split limitation based on sequence
            self.update_insert_max_split_constraint()
            
        except AttributeError:
            pass
    
    def update_min_len_constraint(self, max_value):
        """Update maximum allowed for min_len"""
        try:
            # Update maximum of min_len slider and spinbox
            self.horizontalSlider_min_len.setMaximum(max_value)
            self.spinBox_min_len.setMaximum(max_value)
            
            # If current min_len value exceeds new maximum, adjust it
            if self.horizontalSlider_min_len.value() > max_value:
                self.horizontalSlider_min_len.setValue(max_value)
            if self.spinBox_min_len.value() > max_value:
                self.spinBox_min_len.setValue(max_value)
                
        except AttributeError:
            pass
    
    def validate_min_len_value(self, min_value):
        """Validate that min_len doesn't exceed max_len"""
        try:
            max_value = self.horizontalSlider_max_len.value()
            if min_value > max_value:
                # Adjust value to maximum allowed
                self.horizontalSlider_min_len.setValue(max_value)
                self.spinBox_min_len.setValue(max_value)
                
        except AttributeError:
            pass
    
    def update_min_split_constraint(self, max_value):
        """Update maximum allowed for min_split"""
        try:
            # Update maximum of min_split slider and spinbox
            self.horizontalSlider_insert_min_split.setMaximum(max_value)
            self.spinBox_insert_min_split.setMaximum(max_value)
            
            # If current min_split value exceeds new maximum, adjust it
            if self.horizontalSlider_insert_min_split.value() > max_value:
                self.horizontalSlider_insert_min_split.setValue(max_value)
            if self.spinBox_insert_min_split.value() > max_value:
                self.spinBox_insert_min_split.setValue(max_value)
                
        except AttributeError:
            pass
    
    def validate_min_split_value(self, min_value):
        """Validate that min_split doesn't exceed max_split"""
        try:
            max_value = self.horizontalSlider_insert_max_split.value()
            if min_value > max_value:
                # Adjust value to maximum allowed
                self.horizontalSlider_insert_min_split.setValue(max_value)
                self.spinBox_insert_min_split.setValue(max_value)
                
        except AttributeError:
            pass
    
    def update_min_reps_constraint(self, max_value):
        """Update maximum allowed for min_reps"""
        try:
            # Update maximum of min_reps slider and spinbox
            self.horizontalSlider_min_reps.setMaximum(max_value)
            self.spinBox_min_reps.setMaximum(max_value)
            
            # If current min_reps value exceeds new maximum, adjust it
            if self.horizontalSlider_min_reps.value() > max_value:
                self.horizontalSlider_min_reps.setValue(max_value)
            if self.spinBox_min_reps.value() > max_value:
                self.spinBox_min_reps.setValue(max_value)
                
        except AttributeError:
            pass
    
    def validate_min_reps_value(self, min_value):
        """Validate that min_reps doesn't exceed max_reps"""
        try:
            max_value = self.horizontalSlider_max_reps.value()
            if min_value > max_value:
                # Adjust value to maximum allowed
                self.horizontalSlider_min_reps.setValue(max_value)
                self.spinBox_min_reps.setValue(max_value)
                
        except AttributeError:
            pass
    
    def update_insert_max_split_constraint(self):
        """Update maximum allowed for max_split based on sequence length"""
        try:
            sequence_text = self.lineEdit_insert_seq.text().strip()
            if sequence_text:
                max_split_value = max(0, len(sequence_text) - 2)
            else:
                max_split_value = 0
            
            # Update maximum of max_split slider and spinbox
            self.horizontalSlider_insert_max_split.setMaximum(max_split_value)
            self.spinBox_insert_max_split.setMaximum(max_split_value)
            
            # If current value exceeds new maximum, adjust it
            if self.horizontalSlider_insert_max_split.value() > max_split_value:
                self.horizontalSlider_insert_max_split.setValue(max_split_value)
            if self.spinBox_insert_max_split.value() > max_split_value:
                self.spinBox_insert_max_split.setValue(max_split_value)
            
            # Also update min_split limitation
            self.update_min_split_constraint(self.horizontalSlider_insert_max_split.value())
                
        except AttributeError:
            pass
    
    def setup_initial_state(self):
        """Configure initial interface state"""
        # Disable batch configuration group initially
        try:
            self.group_configuration.setEnabled(False)
            
            # Disable insert and repeat editing groups initially
            self.group_insert_edit.setEnabled(False)
            self.group_repeat_edit.setEnabled(False)
            
            # Disable generate button initially (no saved config)
            self.btn_generate.setEnabled(False)
            
            # Disable new sequence button initially (no text in base_id)
            self.btn_new_seq.setEnabled(False)
            
            # Configure tables
            self.setup_tables()
            
            # Default values
            self.set_default_values()
            
            # Initial validation of proportion sum
            self.validate_proportion_sum()
            
        except AttributeError:
            pass
    
    def setup_tables(self):
        """Configure insert and repeat tables"""
        try:
            # Configure insert table
            self.table_inserts.setColumnCount(1)
            self.table_inserts.setHorizontalHeaderLabels(["Sequence"])
            # Make header stretch to full width
            self.table_inserts.horizontalHeader().setStretchLastSection(True)
            # Make items non-editable
            self.table_inserts.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            
            # Configure repeat table
            self.table_repeats.setColumnCount(1)
            self.table_repeats.setHorizontalHeaderLabels(["Pattern"])
            # Make header stretch to full width
            self.table_repeats.horizontalHeader().setStretchLastSection(True)
            # Make items non-editable
            self.table_repeats.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            
        except AttributeError:
            pass
    
    def set_default_values(self):
        """Set default values"""
        try:
            # General default values
            self.spinBox_id_padding.setValue(4)
            self.spinBox_seq_wrap.setValue(70)
            
            # Default proportions (0.25 each)
            self.doubleSpinBox_A.setValue(0.25)
            self.doubleSpinBox_T.setValue(0.25)
            self.doubleSpinBox_C.setValue(0.25)
            self.doubleSpinBox_G.setValue(0.25)
            
        except AttributeError:
            pass
    
    def add_new_sequence(self):
        """Add new sequence to list"""
        try:
            base_id = self.lineEdit_base_id.text().strip()
            if not base_id:
                QMessageBox.warning(self, "Warning", "Please enter a Base ID")
                return
            
            if base_id in self.sequences_data:
                QMessageBox.warning(self, "Warning", "Base ID already exists")
                return
            
            # Create new data entry
            self.sequences_data[base_id] = {
                "base_id": base_id,
                "generate": 0,
                "max_len": 1000,
                "min_len": 500,
                "proportion": {"A": 0.25, "T": 0.25, "C": 0.25, "G": 0.25},
                "repeats": [],
                "inserts": []
            }
            
            # Add to model
            current_list = self.sequence_model.stringList()
            current_list.append(base_id)
            self.sequence_model.setStringList(current_list)
            
            # Clear input field
            self.lineEdit_base_id.clear()
            
            # Select new item
            last_index = self.sequence_model.index(len(current_list) - 1)
            self.sequence_list.setCurrentIndex(last_index)
            
        except AttributeError:
            pass
    
    def remove_sequence(self):
        """Remove selected sequence"""
        try:
            current_index = self.sequence_list.currentIndex()
            if not current_index.isValid():
                return
            
            base_id = self.sequence_model.data(current_index, Qt.ItemDataRole.DisplayRole)
            
            # Confirm deletion
            reply = QMessageBox.question(self, "Confirm", f"Remove sequence '{base_id}'?")
            if reply == QMessageBox.StandardButton.Yes:
                # Remove from data
                if base_id in self.sequences_data:
                    del self.sequences_data[base_id]
                
                # Remove from model
                current_list = self.sequence_model.stringList()
                current_list.remove(base_id)
                self.sequence_model.setStringList(current_list)
                
                # Reset selection
                self.current_sequence = None
                self.group_configuration.setEnabled(False)
                
                # Check if we need to disable generate button
                if not self.sequences_data:
                    self.has_saved_config = False
                    self.update_generate_button_state()
                
        except AttributeError:
            pass
    
    def on_sequence_selection_changed(self, selected, deselected):
        """Handle sequence selection change in list"""
        try:
            current_index = self.sequence_list.currentIndex()
            if current_index.isValid():
                base_id = self.sequence_model.data(current_index, Qt.ItemDataRole.DisplayRole)
                self.current_sequence = base_id
                self.group_configuration.setEnabled(True)
                self.load_sequence_config(base_id)
            else:
                self.current_sequence = None
                self.group_configuration.setEnabled(False)
                # Also disable editing groups
                self.group_insert_edit.setEnabled(False)
                self.group_repeat_edit.setEnabled(False)
                
        except AttributeError:
            pass
    
    def on_sequence_renamed(self, top_left, bottom_right, roles):
        """Handle sequence renaming in QListView"""
        try:
            if Qt.ItemDataRole.DisplayRole in roles:
                # Get new name
                new_name = self.sequence_model.data(top_left, Qt.ItemDataRole.DisplayRole)
                row = top_left.row()
                
                # Get current list to find previous name
                current_list = self.sequence_model.stringList()
                if row < len(current_list):
                    # Find previous name in sequences_data
                    old_names = list(self.sequences_data.keys())
                    if row < len(old_names):
                        old_name = old_names[row]
                        
                        # Verify new name doesn't already exist
                        if new_name != old_name and new_name not in self.sequences_data:
                            # Rename in sequences_data
                            if old_name in self.sequences_data:
                                self.sequences_data[new_name] = self.sequences_data[old_name]
                                self.sequences_data[new_name]["base_id"] = new_name
                                del self.sequences_data[old_name]
                                
                                # Update current_sequence if it was renamed
                                if self.current_sequence == old_name:
                                    self.current_sequence = new_name
                        
                        elif new_name != old_name and new_name in self.sequences_data:
                            # Name already exists, revert change
                            QMessageBox.warning(self, "Warning", "Base ID already exists")
                            current_list = self.sequence_model.stringList()
                            current_list[row] = old_name
                            self.sequence_model.setStringList(current_list)
                            
        except (AttributeError, IndexError, KeyError):
            pass
    
    def load_sequence_config(self, base_id):
        """Load configuration for specific sequence"""
        if base_id not in self.sequences_data:
            return
        
        data = self.sequences_data[base_id]
        
        try:
            # Load random generation configuration
            self.spinBox_generate.setValue(data.get("generate", 0))
            self.spinBox_max_len.setValue(data.get("max_len", 1000))
            self.spinBox_min_len.setValue(data.get("min_len", 500))
            
            # Load tables
            self.load_inserts_table(data.get("inserts", []))
            self.load_repeats_table(data.get("repeats", []))
            
        except AttributeError:
            pass
    
    def load_inserts_table(self, inserts):
        """Load data into insert table"""
        try:
            self.table_inserts.setRowCount(len(inserts))
            for i, insert in enumerate(inserts):
                item = QTableWidgetItem(insert.get("sequence", ""))
                self.table_inserts.setItem(i, 0, item)
        except AttributeError:
            pass
    
    def load_repeats_table(self, repeats):
        """Load data into repeat table"""
        try:
            self.table_repeats.setRowCount(len(repeats))
            for i, repeat in enumerate(repeats):
                item = QTableWidgetItem(repeat.get("pattern", ""))
                self.table_repeats.setItem(i, 0, item)
        except AttributeError:
            pass
    
    def save_random_generation_config(self):
        """Save random generation configuration"""
        if not self.current_sequence:
            return
        
        try:
            data = self.sequences_data[self.current_sequence]
            data["generate"] = self.spinBox_generate.value()
            data["max_len"] = self.spinBox_max_len.value()
            data["min_len"] = self.spinBox_min_len.value()
            
            # Mark that we have saved configuration
            self.has_saved_config = True
            self.update_generate_button_state()
            
            QMessageBox.information(self, "Success", "Random generation configuration saved")
            
        except (AttributeError, KeyError):
            pass
    
    def add_new_insert(self):
        """Add new insert"""
        if not self.current_sequence:
            return
        
        try:
            # Create new insert with default values
            new_insert = {
                "total": 0,
                "max_split": 0,
                "min_split": 0,
                "ave_gap": 0,
                "sd_gap": 0,
                "mutation_rate": 0.0,
                "sequence": ""
            }
            
            data = self.sequences_data[self.current_sequence]
            data["inserts"].append(new_insert)
            
            # Reload table
            self.load_inserts_table(data["inserts"])
            
            # Select new item
            last_row = self.table_inserts.rowCount() - 1
            self.table_inserts.selectRow(last_row)
            
        except (AttributeError, KeyError):
            pass
    
    def remove_insert(self):
        """Remove selected insert"""
        if not self.current_sequence:
            return
        
        try:
            current_row = self.table_inserts.currentRow()
            if current_row < 0:
                return
            
            data = self.sequences_data[self.current_sequence]
            if current_row < len(data["inserts"]):
                del data["inserts"][current_row]
                self.load_inserts_table(data["inserts"])
                
        except (AttributeError, KeyError, IndexError):
            pass
    
    def add_new_repeat(self):
        """Add new repeat"""
        if not self.current_sequence:
            return
        
        try:
            # Create new repeat with default values
            new_repeat = {
                "likelihood": 0.0,
                "pattern": "",
                "pattern_max_reps": 1,
                "pattern_min_reps": 1
            }
            
            data = self.sequences_data[self.current_sequence]
            data["repeats"].append(new_repeat)
            
            # Reload table
            self.load_repeats_table(data["repeats"])
            
            # Select new item
            last_row = self.table_repeats.rowCount() - 1
            self.table_repeats.selectRow(last_row)
            
        except (AttributeError, KeyError):
            pass
    
    def remove_repeat(self):
        """Remove selected repeat"""
        if not self.current_sequence:
            return
        
        try:
            current_row = self.table_repeats.currentRow()
            if current_row < 0:
                return
            
            data = self.sequences_data[self.current_sequence]
            if current_row < len(data["repeats"]):
                del data["repeats"][current_row]
                self.load_repeats_table(data["repeats"])
                
        except (AttributeError, KeyError, IndexError):
            pass
    
    def on_insert_selection_changed(self):
        """Handle selection change in insert table"""
        if not self.current_sequence:
            return
        
        try:
            current_row = self.table_inserts.currentRow()
            if current_row < 0:
                # No selection, disable editing group
                self.group_insert_edit.setEnabled(False)
                return
            
            # There's selection, enable editing group
            self.group_insert_edit.setEnabled(True)
            
            data = self.sequences_data[self.current_sequence]
            if current_row < len(data["inserts"]):
                insert = data["inserts"][current_row]
                
                # Load values into editing widgets
                self.lineEdit_insert_seq.setText(insert.get("sequence", ""))
                self.spinBox_insert_total.setValue(insert.get("total", 0))
                self.spinBox_insert_max_split.setValue(insert.get("max_split", 0))
                self.spinBox_insert_min_split.setValue(insert.get("min_split", 0))
                self.spinBox_insert_ave_gap.setValue(insert.get("ave_gap", 0))
                self.spinBox_insert_sd_gap.setValue(insert.get("sd_gap", 0))
                self.doubleSpinBox_insert_mut_rate.setValue(insert.get("mutation_rate", 0.0))
                
        except (AttributeError, KeyError, IndexError):
            pass
    
    def on_repeat_selection_changed(self):
        """Handle selection change in repeat table"""
        if not self.current_sequence:
            return
        
        try:
            current_row = self.table_repeats.currentRow()
            if current_row < 0:
                # No selection, disable editing group
                self.group_repeat_edit.setEnabled(False)
                return
            
            # There's selection, enable editing group
            self.group_repeat_edit.setEnabled(True)
            
            data = self.sequences_data[self.current_sequence]
            if current_row < len(data["repeats"]):
                repeat = data["repeats"][current_row]
                
                # Load values into editing widgets
                self.lineEdit_pattern.setText(repeat.get("pattern", ""))
                self.doubleSpinBox_likelihood.setValue(repeat.get("likelihood", 0.0))
                self.spinBox_max_reps.setValue(repeat.get("pattern_max_reps", 1))
                self.spinBox_min_reps.setValue(repeat.get("pattern_min_reps", 1))
                
        except (AttributeError, KeyError, IndexError):
            pass
    
    def save_insert_config(self):
        """Save insert configuration"""
        if not self.current_sequence:
            return
        
        try:
            current_row = self.table_inserts.currentRow()
            if current_row < 0:
                QMessageBox.warning(self, "Warning", "Please select an insert to save")
                return
            
            data = self.sequences_data[self.current_sequence]
            if current_row < len(data["inserts"]):
                insert = data["inserts"][current_row]
                
                # Update values
                insert["sequence"] = self.lineEdit_insert_seq.text()
                insert["total"] = self.spinBox_insert_total.value()
                insert["max_split"] = self.spinBox_insert_max_split.value()
                insert["min_split"] = self.spinBox_insert_min_split.value()
                insert["ave_gap"] = self.spinBox_insert_ave_gap.value()
                insert["sd_gap"] = self.spinBox_insert_sd_gap.value()
                insert["mutation_rate"] = self.doubleSpinBox_insert_mut_rate.value()
                
                # Update table
                self.load_inserts_table(data["inserts"])
                self.table_inserts.selectRow(current_row)
                
                # Mark that we have saved configuration
                self.has_saved_config = True
                self.update_generate_button_state()
                
                QMessageBox.information(self, "Success", "Insert configuration saved")
                
        except (AttributeError, KeyError, IndexError):
            pass
    
    def save_repeat_config(self):
        """Save repeat configuration"""
        if not self.current_sequence:
            return
        
        try:
            current_row = self.table_repeats.currentRow()
            if current_row < 0:
                QMessageBox.warning(self, "Warning", "Please select a repeat to save")
                return
            
            data = self.sequences_data[self.current_sequence]
            if current_row < len(data["repeats"]):
                repeat = data["repeats"][current_row]
                
                # Update values
                repeat["pattern"] = self.lineEdit_pattern.text()
                repeat["likelihood"] = self.doubleSpinBox_likelihood.value()
                repeat["pattern_max_reps"] = self.spinBox_max_reps.value()
                repeat["pattern_min_reps"] = self.spinBox_min_reps.value()
                
                # Update table
                self.load_repeats_table(data["repeats"])
                self.table_repeats.selectRow(current_row)
                
                # Mark that we have saved configuration
                self.has_saved_config = True
                self.update_generate_button_state()
                
                QMessageBox.information(self, "Success", "Repeat configuration saved")
                
        except (AttributeError, KeyError, IndexError):
            pass
    
    def open_insert_sequence_dialog(self):
        """Open dialog to insert sequence"""
        try:
            current_text = self.lineEdit_insert_seq.text()
            dialog = InsertFormDialog(current_text, self)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_text = dialog.get_text()
                self.lineEdit_insert_seq.setText(new_text)
                
        except AttributeError:
            pass
    
    def select_output_file(self, file_type, file_filter):
        """Select output file and update associated paths"""
        default_names = {
            "report": "report.txt",
            "config": "config.json",
            "fasta": "generated.fasta"
        }
        
        # Determine initial directory
        initial_dir = self.output_directory or os.path.expanduser("~")
        initial_path = os.path.join(initial_dir, default_names.get(file_type, "output"))
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Save {file_type.title()} File", initial_path, file_filter
        )
        
        if file_path:
            # Update output directory
            self.output_directory = os.path.dirname(file_path)
            
            # Update corresponding widget
            try:
                if file_type == "report":
                    self.lineEdit_report.setText(file_path)
                elif file_type == "config":
                    self.lineEdit_config_json.setText(file_path)
                elif file_type == "fasta":
                    self.lineEdit_fasta.setText(file_path)
            except AttributeError:
                pass
            
    def update_current_file_paths(self):
        """Update paths for currently imported config file"""
        if self.current_config_file:
            try:
                # Find and update entry in recent files
                for file_entry in self.recent_files:
                    if file_entry.get('config_path') == self.current_config_file:
                        file_entry['report_path'] = getattr(self.lineEdit_report, 'text', lambda: '')()
                        file_entry['fasta_path'] = getattr(self.lineEdit_fasta, 'text', lambda: '')()
                        file_entry['config_json_path'] = getattr(self.lineEdit_config_json, 'text', lambda: '')()
                        break
                
                # Save updated recent files
                self.save_recent_files()
            except Exception:
                pass
    
    def generate_files(self):
        """Generate output files"""
        try:
            # Check if proportion sum is valid
            if not self.check_proportion_sum_valid():
                QMessageBox.warning(
                    self, 
                    "Proportion Error", 
                    "The sum of proportion values (A, T, C, G) must equal 1.0.\n"
                    "Please adjust the values and try again."
                )
                return
            
            # Build complete configuration
            config = self.build_config()
            
            if not config["sequences"]:
                QMessageBox.warning(self, "Warning", "Please add at least one sequence")
                return
            
            # Get file paths
            fasta_path = getattr(self.lineEdit_fasta, 'text', lambda: '')()
            report_path = getattr(self.lineEdit_report, 'text', lambda: '')()
            config_path = getattr(self.lineEdit_config_json, 'text', lambda: '')()
            
            # Check generation options
            only_report = getattr(self.radioButton_only_report, 'isChecked', lambda: False)()
            only_config = getattr(self.radioButton_only_json, 'isChecked', lambda: False)()
            
            if only_report:
                config_path = None
                fasta_path = None
            elif only_config:
                report_path = None
                fasta_path = None
            
            if not any([fasta_path, report_path, config_path]):
                QMessageBox.warning(self, "Warning", "Please select at least one output file")
                return
            
            # Get seed if enabled
            seed = False
            try:
                if self.group_seed.isChecked():
                    seed_text = self.lineEdit_seed.text().strip()
                    if seed_text:
                        seed = int(seed_text)
            except (AttributeError, ValueError):
                pass
            
            # Generate files
            try:
                from libs.Generator.generator import Generator
                
                generate_output_files(
                    config=config,
                    fasta_path=fasta_path,
                    report_path=report_path,
                    config_path=config_path,
                    seed=seed
                )
                
                QMessageBox.information(self, "Success", "Files generated successfully!")
                
            except ImportError:
                QMessageBox.critical(self, "Error", "Generator module not found. Please ensure libs.Generator.generator is available.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error generating files: {str(e)}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unexpected error: {str(e)}")
    
    def build_config(self):
        """Build complete configuration dictionary"""
        config = {
            "id_padding": 4,
            "seq_wrap": 70,
            "seed": False,
            "sequences": []
        }
        
        try:
            # General configuration
            config["id_padding"] = self.spinBox_id_padding.value()
            config["seq_wrap"] = self.spinBox_seq_wrap.value()
            
            # Handle seed correctly
            if hasattr(self, 'group_seed') and self.group_seed.isChecked():
                seed_text = self.lineEdit_seed.text().strip()
                if seed_text:
                    try:
                        config["seed"] = int(seed_text)
                    except ValueError:
                        config["seed"] = seed_text  # Keep as string if not a number
                else:
                    config["seed"] = False
            else:
                config["seed"] = False
            
            # Get current proportions from GUI
            current_proportions = {
                "A": self.doubleSpinBox_A.value(),
                "T": self.doubleSpinBox_T.value(),
                "C": self.doubleSpinBox_C.value(),
                "G": self.doubleSpinBox_G.value()
            }
            
            # Build sequence list
            for base_id, seq_data in self.sequences_data.items():
                sequence_config = {
                    "base_id": base_id,
                    "generate": seq_data.get("generate", 0),
                    "max_len": seq_data.get("max_len", 1000),
                    "min_len": seq_data.get("min_len", 500),
                    "proportion": current_proportions,  # Use current proportions from GUI
                    "repeats": seq_data.get("repeats", []),
                    "inserts": seq_data.get("inserts", [])
                }
                config["sequences"].append(sequence_config)
                
        except AttributeError:
            pass
        
        return config
    
    def show_about_dialog(self):
        """Show About dialog"""
        dialog = AboutDialog(self)
        dialog.exec()
    
    def import_config(self):
        """Import configuration from JSON file"""
        try:
            # Open file selection dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Configuration",
                os.path.expanduser("~"),
                "JSON files (*.json);;All files (*.*)"
            )
            
            if not file_path:
                return
            
            # Read and parse JSON file
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except json.JSONDecodeError as e:
                QMessageBox.critical(
                    self, 
                    "Import Error", 
                    f"Invalid JSON file: {str(e)}"
                )
                return
            except Exception as e:
                QMessageBox.critical(
                    self, 
                    "Import Error", 
                    f"Error reading file: {str(e)}"
                )
                return
            
            # Validate basic JSON structure
            if not self.validate_config_structure(config):
                QMessageBox.critical(
                    self, 
                    "Import Error", 
                    "Invalid configuration file structure"
                )
                return
            
            # Ask user if they want to replace current configuration
            if self.sequences_data:
                reply = QMessageBox.question(
                    self,
                    "Replace Configuration",
                    "This will replace the current configuration. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            # Load configuration
            self.load_config_into_gui(config)
            
            # Update output directory
            self.output_directory = os.path.dirname(file_path)
            
            # Set current config file
            self.current_config_file = file_path
            
            # Add to recent files
            self.add_to_recent_files(file_path)
            
            QMessageBox.information(
                self, 
                "Import Successful", 
                "Configuration imported successfully!"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Import Error", 
                f"Unexpected error: {str(e)}"
            )
    
    def validate_config_structure(self, config):
        """Validate that JSON has expected structure"""
        try:
            # Check main keys
            required_keys = ["id_padding", "seq_wrap", "sequences"]
            for key in required_keys:
                if key not in config:
                    return False
            
            # Check that sequences is a list
            if not isinstance(config["sequences"], list):
                return False
            
            # Check structure of each sequence
            for seq in config["sequences"]:
                if not isinstance(seq, dict):
                    return False
                
                # Check required keys in each sequence
                seq_required_keys = ["base_id", "generate", "max_len", "min_len", "proportion"]
                for key in seq_required_keys:
                    if key not in seq:
                        return False
                
                # Check proportion structure
                if not isinstance(seq["proportion"], dict):
                    return False
                
                # Check that repeats and inserts are lists (if they exist)
                if "repeats" in seq and not isinstance(seq["repeats"], list):
                    return False
                
                if "inserts" in seq and not isinstance(seq["inserts"], list):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def load_config_into_gui(self, config):
        """Load JSON configuration into GUI"""
        try:
            # Clear current data
            self.clear_current_data()
            
            # Load general configuration
            self.spinBox_id_padding.setValue(config.get("id_padding", 4))
            self.spinBox_seq_wrap.setValue(config.get("seq_wrap", 70))
            
            # Load seed if it exists
            if "seed" in config and config["seed"]:
                if isinstance(config["seed"], (int, str)):
                    self.group_seed.setChecked(True)
                    self.lineEdit_seed.setText(str(config["seed"]))
                else:
                    self.group_seed.setChecked(False)
                    self.lineEdit_seed.clear()
            else:
                self.group_seed.setChecked(False)
                self.lineEdit_seed.clear()
            
            # Load sequences
            sequence_list = []
            for seq_config in config["sequences"]:
                base_id = seq_config["base_id"]
                sequence_list.append(base_id)
                
                # Store sequence data
                self.sequences_data[base_id] = {
                    "base_id": base_id,
                    "generate": seq_config.get("generate", 0),
                    "max_len": seq_config.get("max_len", 1000),
                    "min_len": seq_config.get("min_len", 500),
                    "proportion": seq_config.get("proportion", {"A": 0.25, "T": 0.25, "C": 0.25, "G": 0.25}),
                    "repeats": seq_config.get("repeats", []),
                    "inserts": seq_config.get("inserts", [])
                }
            
            # Update list model
            self.sequence_model.setStringList(sequence_list)
            
            # If there are sequences, select first one and load proportions
            if sequence_list:
                first_index = self.sequence_model.index(0)
                self.sequence_list.setCurrentIndex(first_index)
                
                # Load proportions from first sequence
                first_seq = config["sequences"][0]
                proportion = first_seq.get("proportion", {"A": 0.25, "T": 0.25, "C": 0.25, "G": 0.25})
                self.doubleSpinBox_A.setValue(proportion.get("A", 0.25))
                self.doubleSpinBox_T.setValue(proportion.get("T", 0.25))
                self.doubleSpinBox_C.setValue(proportion.get("C", 0.25))
                self.doubleSpinBox_G.setValue(proportion.get("G", 0.25))
                
                # Mark as having saved config since we imported it
                self.has_saved_config = True
                self.update_generate_button_state()
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Load Error", 
                f"Error loading configuration: {str(e)}"
            )
    
    def clear_current_data(self):
        """Clear all current GUI data"""
        try:
            # Clear sequence data
            self.sequences_data.clear()
            self.current_sequence = None
            
            # Clear list model
            self.sequence_model.setStringList([])
            
            # Disable configuration group
            self.group_configuration.setEnabled(False)
            
            # Clear tables
            self.table_inserts.setRowCount(0)
            self.table_repeats.setRowCount(0)
            
            # Disable editing groups
            self.group_insert_edit.setEnabled(False)
            self.group_repeat_edit.setEnabled(False)
            
            # Reset editing values
            self.lineEdit_insert_seq.clear()
            self.spinBox_insert_total.setValue(0)
            self.spinBox_insert_max_split.setValue(0)
            self.spinBox_insert_min_split.setValue(0)
            self.spinBox_insert_ave_gap.setValue(0)
            self.spinBox_insert_sd_gap.setValue(0)
            self.doubleSpinBox_insert_mut_rate.setValue(0.0)
            
            self.lineEdit_pattern.clear()
            self.doubleSpinBox_likelihood.setValue(0.0)
            self.spinBox_max_reps.setValue(1)
            self.spinBox_min_reps.setValue(1)
            
            # Reset random generation values
            self.spinBox_generate.setValue(0)
            self.spinBox_max_len.setValue(1000)
            self.spinBox_min_len.setValue(500)
            
            # Reset saved config state
            self.has_saved_config = False
            self.update_generate_button_state()
            
        except AttributeError:
            pass

# Function to generate output files (the one you provided)
def generate_output_files(
        config: dict,
        fasta_path: str | None = None,
        report_path: str | None = None,
        config_path: str | None = None,
        seed: int | bool = False
    ):
    """Generate output files using provided configuration"""
    try:
        from libs.Generator.generator import Generator
        
        gen = Generator(config, seed=seed)
        rep, fasta = gen.get_generated_fasta()
        
        if fasta_path:
            with open(fasta_path, mode='w') as f:
                for line in fasta:
                    f.write(f'{line}\n')
        
        if report_path:
            with open(report_path, mode='w') as f:
                for line in rep:
                    f.write(f'{line}\n')
        
        if config_path:
            json_content = json.dumps(config, indent=4)
            with open(config_path, mode='w') as f:
                f.write(json_content)
                
    except ImportError as e:
        raise ImportError(f"Could not import Generator: {e}")
    except Exception as e:
        raise Exception(f"Error generating files: {e}")

def main():
    """Main function"""
    app = QApplication(sys.argv)
    
    # Configure application style
    app.setStyle('Fusion')
    
    try:
        window = SeqModellerMainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
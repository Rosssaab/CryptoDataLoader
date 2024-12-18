import nltk
import os
import sys

def download_nltk_data():
    print("Starting NLTK data download...")
    try:
        # Set NLTK data path to a directory in your project
        nltk_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nltk_data')
        nltk.data.path.append(nltk_data_dir)
        
        # Download required NLTK data
        nltk.download('punkt', download_dir=nltk_data_dir)
        nltk.download('averaged_perceptron_tagger', download_dir=nltk_data_dir)
        nltk.download('maxent_ne_chunker', download_dir=nltk_data_dir)
        nltk.download('words', download_dir=nltk_data_dir)
        nltk.download('vader_lexicon', download_dir=nltk_data_dir)
        
        print("NLTK data downloaded successfully to:", nltk_data_dir)
        return True
    except Exception as e:
        print("Error downloading NLTK data:", str(e))
        return False

if __name__ == '__main__':
    download_nltk_data()
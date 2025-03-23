import yaml
import os
import re
import random
from flask import request, jsonify, send_from_directory
from tools.logger.custom_logging import custom_log
from core.managers.module_manager import ModuleManager

class QuestionModule:
    def __init__(self, app_manager=None):
        """Initialize QuestionModule and register routes."""
        self.app_manager = app_manager
        self.connection_module = self.get_connection_module()
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.IMAGE_DIR = os.path.join(self.BASE_DIR, "celeb_data", "images")
        self.NAMES_YAML_PATH = os.path.join(self.BASE_DIR, "celeb_data", "categoriesed_celeb_names_for_db_populate.yml")
        self.DATA_YAML_PATH = os.path.join(self.BASE_DIR, "celeb_data", "celeb_data.yml")

        if not self.connection_module:
            raise RuntimeError("QuestionModule: Failed to retrieve ConnectionModule from ModuleManager.")

        custom_log("✅ QuestionModule initialized.")

        # ✅ Ensure routes are registered upon module initialization
        self.register_routes()


    def get_connection_module(self):
        """Retrieve ConnectionModule from ModuleManager."""
        module_manager = self.app_manager.module_manager if self.app_manager else ModuleManager()
        return module_manager.get_module("connection_module")

    def register_routes(self):
        """Register question-related routes."""
        if not self.connection_module:
            raise RuntimeError("ConnectionModule is not available yet.")

        # ✅ Register the get-question route
        self.connection_module.register_route('/get-question', self.get_question, methods=['POST'])
        custom_log("🌐 QuestionModule: `/get-question` route registered.")

        # ✅ Register the static image serving route
        def serve_image(filename):
            """Serves images from the /images/ directory."""
            return send_from_directory(self.IMAGE_DIR, filename)

        self.connection_module.register_route('/images/<path:filename>', serve_image, methods=['GET'])
        custom_log("🖼️ QuestionModule: `/images/<filename>` route registered to serve static images.")

    def load_yaml(self, file_path):
        """Load and return YAML data from a given file path."""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return yaml.safe_load(file)
        except Exception as e:
            custom_log(f"❌ Error loading YAML from {file_path}: {e}")
            return None

    def normalize_name(self, name):
        """Normalize a celebrity name for consistent searching."""
        name = name.lower().strip()
        name = name.replace(" ", "_")
        return name

    def get_question(self):
        """Fetch a question using the new `celeb_names.yml` structure and look up facts in `celeb_data.yml`."""
        try:
            custom_log("🔄 Starting get_question request...")

            # ✅ Extract request data
            data = request.get_json()
            level = str(data.get("level", 1))  # Convert level to string (since YAML keys are strings)
            category = data.get("category", "mixed").lower()
            guessed_list = [name.lower() for name in data.get("guessed_names", [])]

            custom_log(f"📥 Received request for category '{category}' at level {level}. Guessed list: {guessed_list}")

            # ✅ Load names YAML
            names_data = self.load_yaml(self.NAMES_YAML_PATH)
            if not names_data or level not in names_data:
                custom_log(f"❌ No data found for level {level}.")
                return jsonify({"error": f"No data available for level {level}"}), 404

            # ✅ Filter available names for the requested category
            level_data = names_data[level]
            if category != "mixed":
                available_names = level_data.get(category, [])
                custom_log(f"✅ Available names for category '{category}' at level {level}: {available_names}")
            else:
                available_names = [name for cat_list in level_data.values() for name in cat_list]  # Flatten all categories
                custom_log(f"✅ Available names for 'mixed' category at level {level}: {available_names}")

            # ✅ Remove already guessed names first
            available_names = [name for name in available_names if name not in guessed_list]

            # ✅ Shuffle AFTER filtering guessed names
            random.shuffle(available_names)  

            if not available_names:
                custom_log(f"⚠️ No more names left to guess in category '{category}' at level {level}.")
                return jsonify({"error": f"No more names left to guess in category '{category}' at level {level}"}), 200

            # ✅ Randomly select a main celebrity
            selected_name = available_names[0]
            custom_log(f"🎭 Selected name: {selected_name}")


            # ✅ Load full celeb data YAML to get the selected name's facts
            celeb_data = self.load_yaml(self.DATA_YAML_PATH)
            if not celeb_data or level not in celeb_data or selected_name not in celeb_data[level]:
                custom_log(f"❌ Could not find details for {selected_name} in `celeb_data.yml`.")
                return jsonify({"error": f"Data for {selected_name} not found"}), 500

            # ✅ Retrieve details for selected celebrity
            selected_data = celeb_data[level][selected_name]
            selected_facts = selected_data.get("facts", [])

            # ✅ Select 3 random facts (if available)
            if len(selected_facts) > 3:
                selected_facts = random.sample(selected_facts, 3)

            custom_log(f"📜 Selected 3 Random Facts: {selected_facts}")

            selected_categories = selected_data.get("categories", [])

            if not selected_categories:
                custom_log(f"❌ No category found for {selected_name} in `celeb_data.yml`.")
                return jsonify({"error": f"No category found for {selected_name}"}), 500

            selected_category = selected_categories[0].lower()  # ✅ Use the first category

            # ✅ Select distractor names from the same category
            all_category_names = level_data.get(selected_category, [])
            distractor_names = [name for name in all_category_names if name != selected_name]

            # ✅ Shuffle distractors properly
            random.shuffle(distractor_names)
            distractor_names = distractor_names[:2]  # Pick up to 3 distractors

            # ✅ If not enough distractors, fill from other categories
            if len(distractor_names) < 2:
                additional_names = [name for name in available_names if name not in distractor_names and name != selected_name]
                random.shuffle(additional_names)
                distractor_names.extend(additional_names[:2 - len(distractor_names)])

            custom_log(f"🎭 Final Distractor Names: {distractor_names}")


            # ✅ Get images for selected celebrity and distractors
            image_url = self.get_image_url(selected_name)

            # ✅ Construct response
            response = {
                "name": selected_name,
                "category": selected_category,
                "facts": selected_facts,
                "level": level,
                "image_url": image_url,
                "distractor_names": distractor_names
            }

            custom_log(f"✅ Sending response: {response}")
            return jsonify(response), 200

        except Exception as e:
            custom_log(f"❌ Unexpected error in get_question: {e}")
            return jsonify({"error": f"Server error: {str(e)}"}), 500

    def get_image_url(self, name):
        """Retrieve the image URL for a given name from the images directory."""
        formatted_name = self.normalize_name(name)
        for filename in os.listdir(self.IMAGE_DIR):
            if filename.lower().startswith(formatted_name.lower()):  # ✅ Case-insensitive file matching
                return f"{request.host_url.rstrip('/')}/images/{filename}"

        return f"{request.host_url.rstrip('/')}/images/default.jpg"
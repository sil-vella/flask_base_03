import secrets
import os
from pathlib import Path

def generate_secret(length=32):
    """Generate a secure secret key."""
    return secrets.token_hex(length)

def main():
    # Create secrets directory if it doesn't exist
    secrets_dir = Path("./secrets")
    secrets_dir.mkdir(exist_ok=True)
    
    # Define the secrets we need
    secrets_to_generate = {
        "app_secret_key": 32,  # 32 bytes for Flask SECRET_KEY
        "jwt_secret_key": 32,  # 32 bytes for JWT signing
        "encryption_key": 32,   # 32 bytes for general encryption
    }
    
    # Generate and save each secret
    generated_secrets = {}
    for secret_name, length in secrets_to_generate.items():
        secret_value = generate_secret(length)
        secret_path = secrets_dir / f"{secret_name}.txt"
        
        # Save with restricted permissions (readable only by owner)
        with open(secret_path, 'w') as f:
            f.write(secret_value)
        os.chmod(secret_path, 0o600)
        
        generated_secrets[secret_name] = secret_value
        print(f"Generated {secret_name} and saved to {secret_path}")
    
    print("\nAll secrets generated successfully!")
    print("Make sure to add the 'secrets' directory to .gitignore")

if __name__ == "__main__":
    main() 
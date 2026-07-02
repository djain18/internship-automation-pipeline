import modal
from dotenv import dotenv_values

def sync():
    # Load all values from .env
    env_vars = dotenv_values(".env")
    
    # Filter out empty ones
    clean_vars = {k: v for k, v in env_vars.items() if v is not None}
    
    print(f"Syncing {len(clean_vars)} secrets to 'internship-secrets'...")
    
    try:
        # Correct Modal 0.50+ way to create a PERSISTENT secret:
        # Secret.create is a static method that takes a dict and name
        import modal.cli.secret
        # Actually, the CLI's logic is simpler to call via subprocess for auth etc.
        # But let's try the direct constructor if possible:
        secret = modal.Secret.from_dict(clean_vars)
        # We need to 'deploy' it to name it in the dashboard
        # But wait, Secret.from_dict is used in app.function(secrets=[...])
        # If we want it to show up as a named secret in the dashboard:
        # We use a dummy app deploy or the CLI.
        
        # LEF'S USE THE CLI - it's the standard way.
        # But to avoid shell escaping, we'll write a temp file for the CLI.
        import subprocess
        
        # Format for modal secret create: [key=value ...]
        args = ["modal", "secret", "create", "--force", "internship-secrets"]
        for k, v in clean_vars.items():
            args.append(f"{k}={v}")
        
        print("Running: modal secret create internship-secrets [KEY-VALUE PAIRS]...")
        subprocess.run(args, check=True)
        print("[OK] Successfully synced secrets to Modal via CLI!")
        
    except Exception as e:
        print(f"[FAIL] Failed to sync: {e}")

if __name__ == "__main__":
    sync()

import os
import subprocess

# Получаем текущий путь
current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

try:
    target_commit = "60ae9bee8aa39854dcb8d63d7ace34ffd3267a24"
    print(f"Attempting to reset to commit: {target_commit}...")
    
    # Выполняем команду git reset --hard для указанного коммита
    result = subprocess.run(['git', 'reset', '--hard', target_commit], 
                           check=True, 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE)
    
    # Выводим результат
    print("Command output:", result.stdout.decode())
    print("Hard reset completed successfully!")
    
except subprocess.CalledProcessError as e:
    print("Error executing git command:", e)
    print("Error output:", e.stderr.decode())
    
except Exception as ex:
    print(f"Unexpected error occurred: {ex}")
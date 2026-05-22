import pygame
import sys
import time
import random
import os

# --- CONFIGURATION ---
FPS = 60
BASE_WIDTH, BASE_HEIGHT = 1920, 1080
FONT_NAME = "Arial"

# Background Color
BG_COLOR = (10, 10, 15)

# If your base PNGs for the world are grey/white, this will force them to be colored
# so you can tell them apart (Floor = Green, Wall = Dark Grey, Crate = Brown)
TINT_WORLD_ASSETS = True 

# 16 HIGH-CONTRAST PLAYER COLORS
PLAYER_COLORS = [
    (255, 30, 30),    # 1. Pure Red
    (30, 255, 30),    # 2. Pure Green
    (40, 120, 255),   # 3. Bright Blue
    (255, 255, 20),   # 4. Vibrant Yellow
    (255, 30, 255),   # 5. Hot Pink/Magenta
    (30, 255, 255),   # 6. Cyan
    (255, 128, 0),    # 7. Bright Orange
    (150, 50, 255),   # 8. Purple
    (255, 255, 255),  # 9. White
    (139, 69, 19),    # 10. Saddle Brown
    (255, 150, 150),  # 11. Pastel Pink
    (170, 255, 195),  # 12. Mint Green
    (0, 128, 128),    # 13. Teal
    (230, 190, 255),  # 14. Lavender
    (191, 255, 0),    # 15. Lime
    (150, 150, 150)   # 16. Light Gray
]

BTN_A = 0
BTN_B = 1
BTN_SELECT = 2
BTN_START = 3

def tint_image(image, color):
    """Tints a Pygame surface with a color while preserving transparency."""
    tinted = image.copy()
    tinted.fill(color, special_flags=pygame.BLEND_RGBA_MULT)
    return tinted

def create_fallback(color, size=(16, 16)):
    surf = pygame.Surface(size, pygame.SRCALPHA)
    surf.fill(color)
    return surf

class Player:
    def __init__(self, joy_id, instance_id, nickname, color, base_img):
        self.joy_id = joy_id
        self.instance_id = instance_id
        self.nickname = nickname
        self.color = color
        self.base_img = base_img 
        self.sprite = None       
        
        self.ready = False
        self.voted_quit = self.voted_yes = self.voted_no = False
        
        self.score = 0
        self.reset()

    def reset(self):
        self.alive = True
        self.grid_x = 0
        self.grid_y = 0
        self.max_bombs = 1
        self.active_bombs = 0
        self.bomb_range = 2
        self.move_delay = 180 
        self.move_cooldown = 0

    def update(self, dt, joystick, grid, bombs, cols, rows):
        if not self.alive: return

        if self.move_cooldown > 0: self.move_cooldown -= dt
            
        if self.move_cooldown <= 0:
            axis_x = joystick.get_axis(0)
            axis_y = joystick.get_axis(1)
            
            dx, dy = 0, 0
            if axis_x < -0.5: dx = -1
            elif axis_x > 0.5: dx = 1
            elif axis_y < -0.5: dy = -1
            elif axis_y > 0.5: dy = 1
            
            if dx != 0 or dy != 0:
                target_x = self.grid_x + dx
                target_y = self.grid_y + dy
                
                if 0 <= target_x < cols and 0 <= target_y < rows:
                    if grid[target_y][target_x] == 0: 
                        bomb_in_way = any(b.grid_x == target_x and b.grid_y == target_y for b in bombs)
                        if not bomb_in_way:
                            self.grid_x = target_x
                            self.grid_y = target_y
                            self.move_cooldown = self.move_delay

class Bomb:
    def __init__(self, x, y, owner):
        self.grid_x = x
        self.grid_y = y
        self.owner = owner
        self.place_time = time.time()
        self.duration = 3.0 

class Explosion:
    def __init__(self, tiles):
        self.tiles = tiles 
        self.spawn_time = time.time()
        self.duration = 0.5 

class PowerUp:
    def __init__(self, x, y, p_type):
        self.grid_x = x
        self.grid_y = y
        self.type = p_type 

class Game:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        pygame.mixer.init()
        
        self.screen = pygame.display.set_mode((BASE_WIDTH, BASE_HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
        pygame.display.set_caption("16-Player Bomberman Server")
        self.clock = pygame.time.Clock()
        
        self.font = pygame.font.SysFont(FONT_NAME, 24, bold=True)
        self.small_font = pygame.font.SysFont(FONT_NAME, 16, bold=True)
        self.title_font = pygame.font.SysFont(FONT_NAME, 64, bold=True)
        
        self.joysticks = {}
        self.players = {}
        self.color_idx = 0
        
        self.state = "MENU"
        self.previous_state = "MENU"
        
        self.cols, self.rows = 15, 11
        self.tile_size = 60
        self.offset_x, self.offset_y = 0, 0
        
        self.grid = []
        self.static_bg = None 
        self.bombs = []
        self.explosions = []
        self.powerups = []
        
        self.raw_assets = {}
        self.scaled_assets = {}
        self.load_assets()

    def load_image_or_fallback(self, filename, fallback_color, tint=False):
        path = os.path.join("assets", filename)
        if os.path.exists(path):
            img = pygame.image.load(path).convert_alpha()
            if tint and TINT_WORLD_ASSETS:
                return tint_image(img, fallback_color)
            return img
        else:
            print(f"[Warning] Missing {filename}, using fallback color.")
            return create_fallback(fallback_color)

    def load_assets(self):
        self.playlist = []
        if os.path.exists('music'):
            self.playlist = [os.path.join('music', f) for f in os.listdir('music') if f.endswith(('.mp3', '.ogg', '.wav'))]
        if self.playlist: pygame.mixer.music.load(self.playlist[0])

        # World Assets (Forced Tinting enabled to fix the grey/purple monochrome issue)
        self.raw_assets['floor'] = self.load_image_or_fallback("floor.png", (40, 130, 40), tint=True)   # Deep Green
        self.raw_assets['wall'] = self.load_image_or_fallback("wall.png", (50, 50, 60), tint=True)      # Dark Slate
        self.raw_assets['block'] = self.load_image_or_fallback("block.png", (180, 100, 50), tint=True)  # Wood Brown
        self.raw_assets['bomb'] = self.load_image_or_fallback("bomb.png", (30, 30, 30))
        self.raw_assets['explosion'] = self.load_image_or_fallback("explosion.png", (255, 140, 0))
        
        # PowerUps
        self.raw_assets['powerup_0'] = self.load_image_or_fallback("powerup1.png", (200, 200, 200)) # Bomb       
        self.raw_assets['powerup_1'] = self.load_image_or_fallback("powerup2.png", (255, 69, 0))    # Range
        self.raw_assets['powerup_2'] = self.load_image_or_fallback("powerup3.png", (0, 191, 255))   # Speed

        # Hero Sprites
        self.hero_images = []
        for i in range(1, 5):
            self.hero_images.append(self.load_image_or_fallback(f"hero{i}.png", (255, 255, 255)))

    def scale_world_assets(self):
        size = (self.tile_size, self.tile_size)
        for key, img in self.raw_assets.items():
            self.scaled_assets[key] = pygame.transform.scale(img, size)

    def reset_all_votes(self):
        for p in self.players.values(): p.voted_quit = p.voted_yes = p.voted_no = False

    def calculate_map_size(self, num_players):
        # Increased map expansion rate to give more room
        extra_players = max(0, num_players - 2)
        self.cols = 15 + (extra_players * 3) 
        self.rows = 11 + (extra_players * 2)
        
        if self.cols % 2 == 0: self.cols += 1
        if self.rows % 2 == 0: self.rows += 1
        
        self.tile_size = min(BASE_WIDTH // self.cols, (BASE_HEIGHT - 100) // self.rows)
        self.offset_x = (BASE_WIDTH - (self.cols * self.tile_size)) // 2
        self.offset_y = (BASE_HEIGHT - (self.rows * self.tile_size)) // 2 + 30

    def generate_level(self):
        self.bombs.clear()
        self.explosions.clear()
        self.powerups.clear()
        
        # 1. Build Base Grid
        self.grid = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        for y in range(self.rows):
            for x in range(self.cols):
                if x == 0 or x == self.cols - 1 or y == 0 or y == self.rows - 1 or (x % 2 == 0 and y % 2 == 0):
                    self.grid[y][x] = 1 
                elif random.random() < 0.65: 
                    self.grid[y][x] = 2 

        # 2. Perfect Uniform Perimeter Spawning Algorithm
        perimeter = []
        # Top edge
        for x in range(1, self.cols-1, 2): perimeter.append((x, 1))
        # Right edge
        for y in range(3, self.rows-1, 2): perimeter.append((self.cols-2, y))
        # Bottom edge (right to left)
        for x in range(self.cols-4, 0, -2): perimeter.append((x, self.rows-2))
        # Left edge (bottom to top)
        for y in range(self.rows-4, 1, -2): perimeter.append((1, y))

        # Evenly divide the perimeter among all active players
        num_players = max(1, len(self.players))
        step = len(perimeter) / num_players
        
        spawns = []
        for i in range(num_players):
            idx = int(i * step) % len(perimeter)
            spawns.append(perimeter[idx])
        
        # 3. Assign Players to Spawns and clear surrounding blocks
        for idx, p in enumerate(self.players.values()):
            sx, sy = spawns[idx]
            p.grid_x, p.grid_y = sx, sy
            safe_tiles = [(sx, sy), (sx+1, sy), (sx-1, sy), (sx, sy+1), (sx, sy-1), (sx+2, sy), (sx-2, sy), (sx, sy+2), (sx, sy-2)]
            for (tx, ty) in safe_tiles:
                if 0 <= tx < self.cols and 0 <= ty < self.rows and self.grid[ty][tx] == 2:
                    self.grid[ty][tx] = 0

        # 4. Bake Static Background Map
        map_w = self.cols * self.tile_size
        map_h = self.rows * self.tile_size
        self.static_bg = pygame.Surface((map_w, map_h))
        
        for y in range(self.rows):
            for x in range(self.cols):
                self.static_bg.blit(self.scaled_assets['floor'], (x * self.tile_size, y * self.tile_size))
                if self.grid[y][x] == 1:
                    self.static_bg.blit(self.scaled_assets['wall'], (x * self.tile_size, y * self.tile_size))

    def start_game(self):
        self.reset_all_votes()
        num_players = max(2, len(self.players))
        
        self.calculate_map_size(num_players)
        self.scale_world_assets() 
        
        for p in self.players.values(): 
            p.reset()
            size = self.tile_size - 8
            scaled_img = pygame.transform.scale(p.base_img, (size, size))
            p.sprite = tint_image(scaled_img, p.color)

        self.generate_level()
        if self.playlist: pygame.mixer.music.play(-1)
        self.state = "PLAYING"

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: return False
                
            elif event.type == pygame.JOYDEVICEADDED:
                joy = pygame.joystick.Joystick(event.device_index)
                joy.init()
                iid = joy.get_instance_id()
                
                if iid not in self.players:
                    self.joysticks[iid] = joy
                    raw_name = joy.get_name()
                    nick = raw_name.replace("Gamepad_", "") if raw_name.startswith("Gamepad_") else raw_name
                    
                    color = PLAYER_COLORS[self.color_idx % len(PLAYER_COLORS)]
                    base_img = self.hero_images[self.color_idx % len(self.hero_images)]
                    
                    self.color_idx += 1
                    self.players[iid] = Player(event.device_index, iid, nick, color, base_img)

            elif event.type == pygame.JOYDEVICEREMOVED:
                iid = event.instance_id
                if iid in self.players: del self.players[iid]
                if iid in self.joysticks: del self.joysticks[iid]

            elif event.type == pygame.JOYBUTTONDOWN:
                player = self.players.get(event.instance_id)
                if not player: continue

                if self.state == "QUIT_PROMPT":
                    if event.button == BTN_SELECT: player.voted_yes = True; player.voted_no = False
                    elif event.button == BTN_START: player.voted_no = True; player.voted_yes = False
                    if sum(1 for p in self.players.values() if p.voted_yes) >= (len(self.players) // 2) + 1: return False 
                    elif sum(1 for p in self.players.values() if p.voted_no) >= (len(self.players) // 2) + 1: 
                        self.state = self.previous_state; self.reset_all_votes()

                elif self.state == "MENU":
                    if event.button == BTN_SELECT: 
                        player.voted_quit = not player.voted_quit
                        if sum(1 for p in self.players.values() if p.voted_quit) >= (len(self.players) // 2) + 1:
                            self.previous_state = self.state; self.state = "QUIT_PROMPT"; self.reset_all_votes()
                    elif event.button == BTN_START:
                        player.ready = not player.ready

                elif self.state == "PLAYING" and player.alive:
                    if event.button == BTN_A:
                        if player.active_bombs < player.max_bombs:
                            if not any(b.grid_x == player.grid_x and b.grid_y == player.grid_y for b in self.bombs):
                                self.bombs.append(Bomb(player.grid_x, player.grid_y, player))
                                player.active_bombs += 1

                elif self.state == "LEADERBOARD":
                    if event.button == BTN_START:
                        self.state = "MENU"
                        for p in self.players.values(): p.ready = False
        return True

    def update_playing(self, dt):
        current_time = time.time()

        for iid, player in self.players.items():
            if iid in self.joysticks:
                player.update(dt, self.joysticks[iid], self.grid, self.bombs, self.cols, self.rows)
                for p_up in self.powerups[:]:
                    if p_up.grid_x == player.grid_x and p_up.grid_y == player.grid_y:
                        if p_up.type == 0: player.max_bombs = min(8, player.max_bombs + 1)
                        elif p_up.type == 1: player.bomb_range = min(10, player.bomb_range + 1)
                        elif p_up.type == 2: player.move_delay = max(60, player.move_delay - 20)
                        self.powerups.remove(p_up)

        active_bombs = []
        for bomb in self.bombs:
            if current_time - bomb.place_time >= bomb.duration:
                self.explode_bomb(bomb)
                bomb.owner.active_bombs -= 1
            else:
                active_bombs.append(bomb)
        self.bombs = active_bombs

        active_explosions = []
        for exp in self.explosions:
            if current_time - exp.spawn_time < exp.duration:
                active_explosions.append(exp)
                for player in self.players.values():
                    if player.alive and (player.grid_x, player.grid_y) in exp.tiles:
                        player.alive = False
            else: pass
        self.explosions = active_explosions

        alive_players = [p for p in self.players.values() if p.alive]
        if len(self.players) > 1 and len(alive_players) <= 1:
            if len(alive_players) == 1: alive_players[0].score += 1
            pygame.mixer.music.stop()
            self.state = "LEADERBOARD"

    def explode_bomb(self, bomb):
        exp_tiles = [(bomb.grid_x, bomb.grid_y)]
        directions = [(1,0), (-1,0), (0,1), (0,-1)]
        self.powerups = [pu for pu in self.powerups if not (pu.grid_x == bomb.grid_x and pu.grid_y == bomb.grid_y)]
        
        for dx, dy in directions:
            for step in range(1, bomb.owner.bomb_range + 1):
                ex = bomb.grid_x + (dx * step)
                ey = bomb.grid_y + (dy * step)
                if not (0 <= ex < self.cols and 0 <= ey < self.rows): break
                cell = self.grid[ey][ex]
                if cell == 1: break 
                elif cell == 2: 
                    self.grid[ey][ex] = 0
                    exp_tiles.append((ex, ey))
                    if random.random() < 0.25:
                        self.powerups.append(PowerUp(ex, ey, random.randint(0, 2)))
                    break 
                else: 
                    exp_tiles.append((ex, ey))
                    self.powerups = [pu for pu in self.powerups if not (pu.grid_x == ex and pu.grid_y == ey)]
        self.explosions.append(Explosion(exp_tiles))

    def draw_playing(self):
        if self.static_bg: self.screen.blit(self.static_bg, (self.offset_x, self.offset_y))

        for pu in self.powerups:
            px = self.offset_x + pu.grid_x * self.tile_size
            py = self.offset_y + pu.grid_y * self.tile_size
            asset_key = f"powerup_{pu.type}"
            self.screen.blit(self.scaled_assets[asset_key], (px, py))

        for y in range(self.rows):
            for x in range(self.cols):
                if self.grid[y][x] == 2:
                    px = self.offset_x + x * self.tile_size
                    py = self.offset_y + y * self.tile_size
                    self.screen.blit(self.scaled_assets['block'], (px, py))

        for bomb in self.bombs:
            px = self.offset_x + bomb.grid_x * self.tile_size
            py = self.offset_y + bomb.grid_y * self.tile_size
            self.screen.blit(self.scaled_assets['bomb'], (px, py))

        for exp in self.explosions:
            for tx, ty in exp.tiles:
                px = self.offset_x + tx * self.tile_size
                py = self.offset_y + ty * self.tile_size
                self.screen.blit(self.scaled_assets['explosion'], (px, py))

        for p in self.players.values():
            if p.alive:
                px = self.offset_x + p.grid_x * self.tile_size
                py = self.offset_y + p.grid_y * self.tile_size
                
                if p.sprite:
                    self.screen.blit(p.sprite, (px + 4, py + 4))
                
                name_surf = self.small_font.render(p.nickname, True, p.color)
                shadow_surf = self.small_font.render(p.nickname, True, (0,0,0))
                self.screen.blit(shadow_surf, shadow_surf.get_rect(center=(px + self.tile_size//2 + 1, py - 7)))
                self.screen.blit(name_surf, name_surf.get_rect(center=(px + self.tile_size//2, py - 8)))

    def draw_menu(self):
        title = self.title_font.render("16-PLAYER BOMBERMAN", True, (255, 140, 0))
        self.screen.blit(title, (BASE_WIDTH//2 - title.get_width()//2, 80))

        instructions = [
            "Podłącz gamepad, aby dołączyć do gry.",
            "",
            "STEROWANIE KONTROLEREM:",
            "» Krzyżak (D-Pad)  -  Poruszanie się",
            "» Przycisk A (Dół)  -  Podłożenie bomby",
            "» Przycisk START    -  Oznacz jako GOTOWY w lobby",
            "» Przycisk SELECT   -  Głosuj za wyłączeniem gry",
            ""
        ]
        
        y = 170
        for line in instructions:
            color = (255, 215, 0) if "STEROWANIE" in line else (200, 200, 200)
            text = self.font.render(line, True, color)
            self.screen.blit(text, (BASE_WIDTH//2 - text.get_width()//2, y))
            y += 35

        # --- POWERUP KEY MENU INSTRUCTIONS ---
        powerup_info_y = y
        powerup_texts = ["- Zwiększa ilość bomb", "- Zwiększa zasięg wybuchu", "- Zwiększa prędkość ruchu"]
        start_x_pu = BASE_WIDTH//2 - 350
        
        for i in range(3):
            # Draw Powerup Sprite
            pu_sprite = pygame.transform.scale(self.raw_assets[f'powerup_{i}'], (30, 30))
            self.screen.blit(pu_sprite, (start_x_pu, powerup_info_y))
            # Draw Description Text
            desc = self.font.render(powerup_texts[i], True, (255, 255, 255))
            self.screen.blit(desc, (start_x_pu + 40, powerup_info_y + 2))
            
            start_x_pu += 250 # Space out horizontally

        y_start = 520
        col_w = 400
        cols = 4
        for idx, p in enumerate(self.players.values()):
            c = idx % cols
            r = idx // cols
            x = BASE_WIDTH//2 - (col_w * cols)//2 + (c * col_w) + 50
            cy = y_start + (r * 50)
            
            status = "GOTOWY" if p.ready else "OCZEKUJE..."
            color = (50, 255, 50) if p.ready else (255, 50, 50)
            text = self.font.render(f"{p.nickname} - {status}", True, color)
            
            preview_img = pygame.transform.scale(p.base_img, (25, 25))
            self.screen.blit(tint_image(preview_img, p.color), (x, cy))
            self.screen.blit(text, (x + 40, cy))

    def draw_leaderboard(self):
        title = self.title_font.render("TABELA WYNIKÓW", True, (255, 140, 0))
        self.screen.blit(title, (BASE_WIDTH//2 - title.get_width()//2, 100))
        info = self.font.render("Wciśnij START aby wrócić do Lobby", True, (150, 150, 150))
        self.screen.blit(info, (BASE_WIDTH//2 - info.get_width()//2, 180))
        
        y = 300
        for idx, p in enumerate(sorted(self.players.values(), key=lambda p: p.score, reverse=True)):
            color = (255, 215, 0) if idx == 0 else (200, 200, 200)
            text = self.font.render(f"{idx + 1}. {p.nickname} - Zwycięstwa: {p.score}", True, color)
            self.screen.blit(text, (BASE_WIDTH//2 - text.get_width()//2, y))
            y += 40

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS)
            running = self.handle_events()
            
            self.screen.fill(BG_COLOR)
            bg_state = self.previous_state if self.state == "QUIT_PROMPT" else self.state

            if bg_state == "MENU": self.draw_menu()
            elif bg_state == "PLAYING": self.update_playing(dt if self.state != "QUIT_PROMPT" else 0); self.draw_playing()
            elif bg_state == "LEADERBOARD": self.draw_leaderboard()

            if self.state == "MENU":
                total_quit_votes = sum(1 for p in self.players.values() if p.voted_quit)
                if total_quit_votes > 0:
                    req = (len(self.players) // 2) + 1
                    info = self.font.render(f"Głosy wyjścia: {total_quit_votes}/{req} (SELECT)", True, (255, 100, 100))
                    self.screen.blit(info, (BASE_WIDTH//2 - info.get_width()//2, 20))
                    
                if len(self.players) > 1 and all(p.ready for p in self.players.values()):
                    self.start_game()

            pygame.display.flip()
        pygame.quit(); sys.exit()

if __name__ == "__main__":
    Game().run()
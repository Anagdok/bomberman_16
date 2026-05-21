import pygame
import sys
import time
import random
import os

# --- CONFIGURATION ---
FPS = 60
BASE_WIDTH, BASE_HEIGHT = 1920, 1080
FONT_NAME = "Arial"

# Colors
BG_COLOR = (10, 10, 15)
FLOOR_COLOR = (34, 139, 34)
WALL_COLOR = (100, 100, 100)
CRATE_COLOR = (139, 69, 19)
BOMB_COLOR = (20, 20, 20)
EXPLOSION_COLOR = (255, 140, 0)
POWERUP_COLORS = {
    0: (0, 0, 0),       # Bomb+ (Black)
    1: (255, 69, 0),    # Range+ (Red-Orange)
    2: (0, 191, 255)    # Speed+ (Deep Sky Blue)
}

# 16 Player Colors
PLAYER_COLORS = [
    (255, 50, 50), (50, 255, 50), (50, 50, 255), (255, 255, 50),
    (255, 50, 255), (50, 255, 255), (255, 150, 50), (150, 50, 255),
    (255, 255, 255), (150, 150, 150), (255, 100, 100), (100, 255, 100),
    (100, 100, 255), (255, 200, 100), (200, 100, 255), (100, 255, 200)
]

BTN_A = 0
BTN_B = 1
BTN_SELECT = 2
BTN_START = 3

def tint_image(image, color):
    """Tints a Pygame surface with a color while preserving transparency."""
    tinted = image.copy()
    # BLEND_RGBA_MULT multiplies the RGB values while keeping the alpha intact.
    # Best results occur if your base sprite has a lot of white/grayscale.
    tinted.fill(color, special_flags=pygame.BLEND_RGBA_MULT)
    return tinted

class Player:
    def __init__(self, joy_id, instance_id, nickname, color, base_img):
        self.joy_id = joy_id
        self.instance_id = instance_id
        self.nickname = nickname
        self.color = color
        self.base_img = base_img # The raw 16x16 asset
        self.sprite = None       # The scaled & tinted asset used for drawing
        
        self.ready = False
        self.voted_quit = False
        self.voted_yes = False
        self.voted_no = False
        
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

        if self.move_cooldown > 0:
            self.move_cooldown -= dt
            
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
        
        self.load_assets()

    def load_assets(self):
        # Music
        self.playlist = []
        if os.path.exists('music'):
            self.playlist = [os.path.join('music', f) for f in os.listdir('music') if f.endswith(('.mp3', '.ogg', '.wav'))]
        if self.playlist: pygame.mixer.music.load(self.playlist[0])

        # Hero Sprites (hero1.png to hero4.png)
        self.hero_images = []
        for i in range(1, 5):
            path = f"assets/hero{i}.png"
            if os.path.exists(path):
                self.hero_images.append(pygame.image.load(path).convert_alpha())
            else:
                # Fallback if asset is missing: A white 16x16 square
                fallback = pygame.Surface((16, 16), pygame.SRCALPHA)
                fallback.fill((255, 255, 255))
                self.hero_images.append(fallback)

    def reset_all_votes(self):
        for p in self.players.values():
            p.voted_quit = p.voted_yes = p.voted_no = False

    def calculate_map_size(self, num_players):
        extra_space = max(0, ((num_players - 1) // 2) * 2)
        self.cols = 15 + extra_space
        self.rows = 11 + extra_space
        if self.cols % 2 == 0: self.cols += 1
        if self.rows % 2 == 0: self.rows += 1
        
        self.tile_size = min(BASE_WIDTH // self.cols, (BASE_HEIGHT - 100) // self.rows)
        self.offset_x = (BASE_WIDTH - (self.cols * self.tile_size)) // 2
        self.offset_y = (BASE_HEIGHT - (self.rows * self.tile_size)) // 2 + 30

    def generate_level(self):
        self.bombs.clear()
        self.explosions.clear()
        self.powerups.clear()
        
        self.grid = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        for y in range(self.rows):
            for x in range(self.cols):
                if x == 0 or x == self.cols - 1 or y == 0 or y == self.rows - 1 or (x % 2 == 0 and y % 2 == 0):
                    self.grid[y][x] = 1 
                elif random.random() < 0.65: 
                    self.grid[y][x] = 2 

        perimeter = []
        for x in range(1, self.cols-1, 2):
            perimeter.extend([(x, 1), (x, self.rows-2)])
        for y in range(3, self.rows-3, 2):
            perimeter.extend([(1, y), (self.cols-2, y)])
            
        random.shuffle(perimeter)
        spawns = perimeter[:len(self.players)]
        
        for idx, p in enumerate(self.players.values()):
            sx, sy = spawns[idx]
            p.grid_x, p.grid_y = sx, sy
            safe_tiles = [(sx, sy), (sx+1, sy), (sx-1, sy), (sx, sy+1), (sx, sy-1)]
            for (tx, ty) in safe_tiles:
                if 0 <= tx < self.cols and 0 <= ty < self.rows and self.grid[ty][tx] == 2:
                    self.grid[ty][tx] = 0

        map_w = self.cols * self.tile_size
        map_h = self.rows * self.tile_size
        self.static_bg = pygame.Surface((map_w, map_h))
        self.static_bg.fill(FLOOR_COLOR)
        for y in range(self.rows):
            for x in range(self.cols):
                if self.grid[y][x] == 1:
                    rect = pygame.Rect(x * self.tile_size, y * self.tile_size, self.tile_size, self.tile_size)
                    pygame.draw.rect(self.static_bg, WALL_COLOR, rect)

    def start_game(self):
        self.reset_all_votes()
        num_players = max(2, len(self.players))
        self.calculate_map_size(num_players)
        
        # We process players here because tile_size is now finalized for the match
        for p in self.players.values(): 
            p.reset()
            # 1. Scale the 16x16 raw image up to the dynamic grid size
            size = self.tile_size - 12
            scaled_img = pygame.transform.scale(p.base_img, (size, size))
            # 2. Apply the Color Tint
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
                    # Assign them one of the 4 base assets based on join order
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
                        self.state = self.previous_state 
                        self.reset_all_votes()

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
                        if p_up.type == 0: player.max_bombs = min(6, player.max_bombs + 1)
                        elif p_up.type == 1: player.bomb_range = min(8, player.bomb_range + 1)
                        elif p_up.type == 2: player.move_delay = max(60, player.move_delay - 25)
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
            rect = pygame.Rect(self.offset_x + pu.grid_x * self.tile_size + 10, self.offset_y + pu.grid_y * self.tile_size + 10, self.tile_size - 20, self.tile_size - 20)
            pygame.draw.circle(self.screen, POWERUP_COLORS[pu.type], rect.center, self.tile_size // 3)
            t = self.small_font.render("B" if pu.type == 0 else "R" if pu.type == 1 else "S", True, (255,255,255))
            self.screen.blit(t, t.get_rect(center=rect.center))

        for y in range(self.rows):
            for x in range(self.cols):
                if self.grid[y][x] == 2:
                    rect = pygame.Rect(self.offset_x + x * self.tile_size, self.offset_y + y * self.tile_size, self.tile_size, self.tile_size)
                    pygame.draw.rect(self.screen, CRATE_COLOR, rect)
                    pygame.draw.rect(self.screen, (100, 50, 10), rect, 2)

        for bomb in self.bombs:
            center = (self.offset_x + bomb.grid_x * self.tile_size + self.tile_size // 2, self.offset_y + bomb.grid_y * self.tile_size + self.tile_size // 2)
            pygame.draw.circle(self.screen, BOMB_COLOR, center, self.tile_size // 2 - 6)

        for exp in self.explosions:
            for tx, ty in exp.tiles:
                rect = pygame.Rect(self.offset_x + tx * self.tile_size, self.offset_y + ty * self.tile_size, self.tile_size, self.tile_size)
                pygame.draw.rect(self.screen, EXPLOSION_COLOR, rect)

        for p in self.players.values():
            if p.alive:
                px = self.offset_x + p.grid_x * self.tile_size
                py = self.offset_y + p.grid_y * self.tile_size
                rect = pygame.Rect(px + 6, py + 6, self.tile_size - 12, self.tile_size - 12)
                
                # DRAW THE TINTED SPRITE
                if p.sprite:
                    self.screen.blit(p.sprite, rect.topleft)
                else: # Fallback to rectangle
                    pygame.draw.rect(self.screen, p.color, rect)
                
                # Player Nickname
                name_surf = self.small_font.render(p.nickname, True, p.color)
                self.screen.blit(name_surf, name_surf.get_rect(center=(px + self.tile_size//2, py - 8)))

    # -------- MENUS --------
    def draw_menu(self):
        title = self.title_font.render("16-PLAYER BOMBERMAN", True, (255, 140, 0))
        self.screen.blit(title, (BASE_WIDTH//2 - title.get_width()//2, 100))

        y = 220
        for line in ["Podłącz gamepad i naciśnij START aby być gotowym.", "Zniszcz skrzynie by zdobyć (B)omby, (R)ange, (S)peed."]:
            text = self.font.render(line, True, (200, 200, 200))
            self.screen.blit(text, (BASE_WIDTH//2 - text.get_width()//2, y))
            y += 30

        y_start = 350
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
            
            # Show tinted sprite in the lobby as well!
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
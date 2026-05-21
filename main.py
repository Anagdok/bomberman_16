import pygame
import sys
import time
import random

# --- CONFIGURATION ---
FPS = 60
BASE_WIDTH, BASE_HEIGHT = 1920, 1080
TILE_SIZE = 60  # Scaled up for 1080p readability
COLS, ROWS = 21, 13 # Odd numbers work best for Bomberman grids

# Grid Offsets to center the map on screen
MAP_WIDTH = COLS * TILE_SIZE
MAP_HEIGHT = ROWS * TILE_SIZE
OFFSET_X = (BASE_WIDTH - MAP_WIDTH) // 2
OFFSET_Y = (BASE_HEIGHT - MAP_HEIGHT) // 2

# Colors (Placeholder for assets)
BG_COLOR = (10, 10, 15)
FLOOR_COLOR = (34, 139, 34)
WALL_COLOR = (100, 100, 100)
CRATE_COLOR = (139, 69, 19)
BOMB_COLOR = (20, 20, 20)
EXPLOSION_COLOR = (255, 140, 0)

FONT_NAME = "Arial"

# UInput Gamepad Button Mapping (Matched to your Tetris config)
BTN_A = 0
BTN_B = 1
BTN_SELECT = 2
BTN_START = 3

class Player:
    def __init__(self, joy_id, instance_id, nickname, color):
        self.joy_id = joy_id
        self.instance_id = instance_id
        self.nickname = nickname
        self.color = color
        
        # Lobby Voting Flags
        self.ready = False
        self.voted_quit = False
        self.voted_yes = False
        self.voted_no = False
        
        self.score = 0
        self.reset()

    def reset(self):
        self.alive = True
        self.grid_x = 1
        self.grid_y = 1
        self.max_bombs = 1
        self.active_bombs = 0
        self.bomb_range = 2
        
        # Movement logic
        self.move_cooldown = 0
        self.move_delay = 150 # milliseconds between grid steps

    def update(self, dt, joystick, grid, bombs):
        if not self.alive: return

        # Handle movement cooldown
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
                
                # Check grid bounds and obstacles (0 = Floor)
                if 0 <= target_x < COLS and 0 <= target_y < ROWS:
                    if grid[target_y][target_x] == 0:
                        # Ensure we aren't walking into a bomb
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
        self.tiles = tiles # List of (grid_x, grid_y) tuples
        self.spawn_time = time.time()
        self.duration = 0.5 

class Game:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        
        self.screen = pygame.display.set_mode((BASE_WIDTH, BASE_HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
        pygame.display.set_caption("Gamepad-Server Bomberman")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(FONT_NAME, 24, bold=True)
        self.small_font = pygame.font.SysFont(FONT_NAME, 16)
        self.title_font = pygame.font.SysFont(FONT_NAME, 64, bold=True)
        
        self.joysticks = {}
        self.players = {}
        self.player_colors = [(255, 50, 50), (50, 255, 50), (50, 50, 255), (255, 255, 50)]
        self.color_idx = 0
        
        self.state = "MENU"
        self.previous_state = "MENU"
        
        # Grid definition: 0 = Empty, 1 = Solid Wall, 2 = Crate
        self.grid = [[0 for _ in range(COLS)] for _ in range(ROWS)]
        self.static_bg = None 
        self.bombs = []
        self.explosions = []

    def reset_all_votes(self):
        for p in self.players.values():
            p.voted_quit = False
            p.voted_yes = False
            p.voted_no = False

    def generate_level(self):
        self.bombs.clear()
        self.explosions.clear()
        
        # 1. Populate Logic Grid
        for y in range(ROWS):
            for x in range(COLS):
                if x == 0 or x == COLS - 1 or y == 0 or y == ROWS - 1 or (x % 2 == 0 and y % 2 == 0):
                    self.grid[y][x] = 1 # Solid Wall
                elif (x > 2 or y > 2) and random.random() < 0.6: 
                    # Leave top-left (1,1), (1,2), (2,1) empty for spawn, random crates elsewhere
                    self.grid[y][x] = 2 # Crate
                else:
                    self.grid[y][x] = 0 # Floor
                    
        # Force bottom-right, top-right, bottom-left empty for other spawn points
        safe_zones = [(1,1), (1,2), (2,1), 
                      (COLS-2, ROWS-2), (COLS-3, ROWS-2), (COLS-2, ROWS-3),
                      (COLS-2, 1), (COLS-2, 2), (COLS-3, 1),
                      (1, ROWS-2), (2, ROWS-2), (1, ROWS-3)]
        for (sx, sy) in safe_zones:
            if self.grid[sy][sx] == 2: self.grid[sy][sx] = 0

        # 2. Pre-render Static Background (Performance Boost)
        self.static_bg = pygame.Surface((MAP_WIDTH, MAP_HEIGHT))
        self.static_bg.fill(FLOOR_COLOR)
        for y in range(ROWS):
            for x in range(COLS):
                if self.grid[y][x] == 1:
                    rect = pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                    pygame.draw.rect(self.static_bg, WALL_COLOR, rect)

    def start_game(self):
        self.reset_all_votes()
        self.generate_level()
        
        # Spawn players in corners
        spawns = [(1, 1), (COLS-2, ROWS-2), (COLS-2, 1), (1, ROWS-2)]
        for idx, p in enumerate(self.players.values()): 
            p.reset()
            sx, sy = spawns[idx % len(spawns)]
            p.grid_x = sx
            p.grid_y = sy
            
        self.state = "PLAYING"

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
                
            elif event.type == pygame.JOYDEVICEADDED:
                joy = pygame.joystick.Joystick(event.device_index)
                joy.init()
                iid = joy.get_instance_id()
                self.joysticks[iid] = joy
                
                raw_name = joy.get_name()
                nickname = raw_name.replace("Gamepad_", "") if raw_name.startswith("Gamepad_") else raw_name
                color = self.player_colors[self.color_idx % len(self.player_colors)]
                self.color_idx += 1
                
                self.players[iid] = Player(event.device_index, iid, nickname, color)
                print(f"[Engine] Player Joined: {nickname}")

            elif event.type == pygame.JOYDEVICEREMOVED:
                iid = event.instance_id
                if iid in self.players:
                    del self.players[iid]
                if iid in self.joysticks:
                    del self.joysticks[iid]

            elif event.type == pygame.JOYBUTTONDOWN:
                player = self.players.get(event.instance_id)
                if not player: continue

                # --- QUIT PROMPT STATE ---
                if self.state == "QUIT_PROMPT":
                    if event.button == BTN_SELECT: player.voted_yes = True; player.voted_no = False
                    elif event.button == BTN_START: player.voted_no = True; player.voted_yes = False
                        
                    yes_votes = sum(1 for p in self.players.values() if p.voted_yes)
                    no_votes = sum(1 for p in self.players.values() if p.voted_no)
                    majority = (len(self.players) // 2) + 1 
                    
                    if yes_votes >= majority: return False 
                    elif no_votes >= majority: 
                        self.state = self.previous_state 
                        self.reset_all_votes()

                # --- MENU STATE ---
                elif self.state == "MENU":
                    if event.button == BTN_SELECT: 
                        player.voted_quit = not player.voted_quit
                        majority = (len(self.players) // 2) + 1
                        if sum(1 for p in self.players.values() if p.voted_quit) >= majority:
                            self.previous_state = self.state
                            self.state = "QUIT_PROMPT"
                            self.reset_all_votes()
                    elif event.button == BTN_START:
                        player.ready = not player.ready

                # --- PLAYING STATE ---
                elif self.state == "PLAYING" and player.alive:
                    if event.button == BTN_A: # Place Bomb
                        if player.active_bombs < player.max_bombs:
                            bomb_exists = any(b.grid_x == player.grid_x and b.grid_y == player.grid_y for b in self.bombs)
                            if not bomb_exists:
                                self.bombs.append(Bomb(player.grid_x, player.grid_y, player))
                                player.active_bombs += 1

                # --- LEADERBOARD STATE ---
                elif self.state == "LEADERBOARD":
                    if event.button == BTN_START:
                        self.state = "MENU"
                        for p in self.players.values(): p.ready = False

        return True

    def update_playing(self, dt):
        current_time = time.time()

        # 1. Update Players
        for iid, player in self.players.items():
            if iid in self.joysticks:
                player.update(dt, self.joysticks[iid], self.grid, self.bombs)

        # 2. Update Bombs
        active_bombs = []
        for bomb in self.bombs:
            if current_time - bomb.place_time >= bomb.duration:
                self.explode_bomb(bomb)
                bomb.owner.active_bombs -= 1
            else:
                active_bombs.append(bomb)
        self.bombs = active_bombs

        # 3. Update Explosions & Collisions
        active_explosions = []
        for exp in self.explosions:
            if current_time - exp.spawn_time < exp.duration:
                active_explosions.append(exp)
                # Check player deaths against O(1) grid coords
                for p_id, player in self.players.items():
                    if player.alive and (player.grid_x, player.grid_y) in exp.tiles:
                        player.alive = False
            else:
                pass
        self.explosions = active_explosions

        # 4. Check Win Condition
        alive_players = [p for p in self.players.values() if p.alive]
        if len(self.players) > 1 and len(alive_players) <= 1:
            if len(alive_players) == 1:
                alive_players[0].score += 1
            self.state = "LEADERBOARD"

    def explode_bomb(self, bomb):
        exp_tiles = [(bomb.grid_x, bomb.grid_y)]
        directions = [(1,0), (-1,0), (0,1), (0,-1)]
        
        for dx, dy in directions:
            for step in range(1, bomb.owner.bomb_range + 1):
                ex = bomb.grid_x + (dx * step)
                ey = bomb.grid_y + (dy * step)
                
                # Check grid bounds
                if not (0 <= ex < COLS and 0 <= ey < ROWS): break
                
                cell = self.grid[ey][ex]
                if cell == 1: # Wall stops explosion
                    break
                elif cell == 2: # Crate stops explosion but is destroyed
                    self.grid[ey][ex] = 0
                    exp_tiles.append((ex, ey))
                    # Optional: Add points to owner for crate destruction here
                    break
                else: # Floor
                    exp_tiles.append((ex, ey))

        self.explosions.append(Explosion(exp_tiles))

    def draw_menu(self):
        title = self.title_font.render("BOMBERMAN BRAWL", True, (255, 140, 0))
        self.screen.blit(title, (BASE_WIDTH//2 - title.get_width()//2, 100))

        instructions = [
            "Witaj w Bombermanie!",
            "Podłącz gamepad i naciśnij START aby być gotowym.",
            "W grze: D-Pad = Ruch, A = Bomba.",
            "W menu: START = gotowość, SELECT = głosowanie za wyjściem.",
        ]
        y = 220
        for line in instructions:
            text = self.small_font.render(line, True, (200, 200, 200))
            self.screen.blit(text, (BASE_WIDTH//2 - text.get_width()//2, y))
            y += 30

        y = 420
        square_w = 20
        gap = 10
        for p in self.players.values():
            status = "GOTOWY" if p.ready else "OCZEKUJE..."
            color = (50, 255, 50) if p.ready else (255, 50, 50)
            text = self.font.render(f"{p.nickname} - {status}", True, color)
            total_w = square_w + gap + text.get_width()
            start_x = BASE_WIDTH//2 - total_w//2
            pygame.draw.rect(self.screen, p.color, (start_x, y, square_w, square_w))
            self.screen.blit(text, (start_x + square_w + gap, y))
            y += 40

    def draw_playing(self):
        # 1. Blit static cached background
        if self.static_bg:
            self.screen.blit(self.static_bg, (OFFSET_X, OFFSET_Y))

        # 2. Draw Dynamic Grid Elements (Crates)
        for y in range(ROWS):
            for x in range(COLS):
                if self.grid[y][x] == 2:
                    rect = pygame.Rect(OFFSET_X + x * TILE_SIZE, OFFSET_Y + y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                    pygame.draw.rect(self.screen, CRATE_COLOR, rect)
                    # To use images: self.screen.blit(crate_img, rect.topleft)

        # 3. Draw Bombs
        for bomb in self.bombs:
            center_x = OFFSET_X + bomb.grid_x * TILE_SIZE + TILE_SIZE // 2
            center_y = OFFSET_Y + bomb.grid_y * TILE_SIZE + TILE_SIZE // 2
            pygame.draw.circle(self.screen, BOMB_COLOR, (center_x, center_y), TILE_SIZE // 2 - 4)

        # 4. Draw Explosions
        for exp in self.explosions:
            for tx, ty in exp.tiles:
                rect = pygame.Rect(OFFSET_X + tx * TILE_SIZE, OFFSET_Y + ty * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                pygame.draw.rect(self.screen, EXPLOSION_COLOR, rect)

        # 5. Draw Players
        for p in self.players.values():
            if p.alive:
                px = OFFSET_X + p.grid_x * TILE_SIZE
                py = OFFSET_Y + p.grid_y * TILE_SIZE
                
                # Player Hitbox/Sprite
                rect = pygame.Rect(px + 4, py + 4, TILE_SIZE - 8, TILE_SIZE - 8)
                pygame.draw.rect(self.screen, p.color, rect)
                
                # Nickname Tag
                name_surf = self.small_font.render(p.nickname, True, (255,255,255))
                name_rect = name_surf.get_rect(center=(px + TILE_SIZE//2, py - 10))
                self.screen.blit(name_surf, name_rect)

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
            y += 50

    def draw_quit_prompt(self):
        s = pygame.Surface((BASE_WIDTH, BASE_HEIGHT), pygame.SRCALPHA)
        s.fill((0, 0, 0, 220)) 
        self.screen.blit(s, (0, 0))
        
        y_center = BASE_HEIGHT // 2
        t1 = self.title_font.render("CZY NA PEWNO CHCESZ WYŁĄCZYĆ GRĘ DO SYSTEMU?", True, (255, 50, 50))
        t2 = self.font.render("Wciśnij SELECT by potwierdzić. Wciśnij START by anulować.", True, (255, 255, 255))
        
        self.screen.blit(t1, (BASE_WIDTH//2 - t1.get_width()//2, y_center - 100))
        self.screen.blit(t2, (BASE_WIDTH//2 - t2.get_width()//2, y_center - 20))
        
        yes_votes = sum(1 for p in self.players.values() if p.voted_yes)
        no_votes = sum(1 for p in self.players.values() if p.voted_no)
        majority = (len(self.players) // 2) + 1
        
        v_text = self.font.render(f"WYJŚCIE: {yes_votes}/{majority} głosów   |   ANULOWANIE: {no_votes}/{majority} głosów", True, (255, 215, 0))
        self.screen.blit(v_text, (BASE_WIDTH//2 - v_text.get_width()//2, y_center + 50))

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS)
            
            running = self.handle_events()
            
            self.screen.fill(BG_COLOR)
            bg_state = self.previous_state if self.state == "QUIT_PROMPT" else self.state

            if bg_state == "MENU":
                self.draw_menu()
            elif bg_state == "PLAYING":
                self.update_playing(dt if self.state != "QUIT_PROMPT" else 0)
                self.draw_playing()
            elif bg_state == "LEADERBOARD":
                self.draw_leaderboard()

            # Lobby overlays
            if self.state == "MENU":
                total_quit_votes = sum(1 for p in self.players.values() if p.voted_quit)
                if total_quit_votes > 0:
                    majority = (len(self.players) // 2) + 1
                    vote_info = self.font.render(f"Głosy za wyłączeniem gry: {total_quit_votes} / {majority} (Wciśnij SELECT)", True, (255, 100, 100))
                    self.screen.blit(vote_info, (BASE_WIDTH//2 - vote_info.get_width()//2, 20))

            if self.state == "QUIT_PROMPT":
                self.draw_quit_prompt()

            # Auto-start Game Condition
            if self.state == "MENU":
                if len(self.players) > 1 and all(p.ready for p in self.players.values()):
                    self.start_game()

            pygame.display.flip()
            
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = Game()
    game.run()
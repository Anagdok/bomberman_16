import pygame
import sys
import time

# --- Game Configuration ---
TILE_SIZE = 40
COLS, ROWS = 15, 11
WIDTH, HEIGHT = COLS * TILE_SIZE, ROWS * TILE_SIZE
FPS = 30

# Colors
BG_COLOR = (34, 139, 34)       # Grass Green
WALL_COLOR = (100, 100, 100)   # Solid Gray
CRATE_COLOR = (139, 69, 19)    # Wood Brown
BOMB_COLOR = (20, 20, 20)      # Black
EXPLOSION_COLOR = (255, 140, 0) # Orange
TEXT_COLOR = (255, 255, 255)

# Gamepad Button Mapping (Standard SDL2 / Pygame mappings for UInput)
BTN_A = 0
BTN_B = 1
BTN_SELECT = 4  # Varies by OS/SDL version, usually 4 or 6
BTN_START = 6   # Varies by OS/SDL version, usually 6 or 7

class Player:
    def __init__(self, joy_id, instance_id, nickname, color):
        self.joy_id = joy_id            # Pygame joystick index
        self.instance_id = instance_id  # Pygame 2.x unique instance ID (handles hotplugging)
        self.nickname = nickname
        self.color = color
        
        # Start at top-left (would normally randomize or set spawn points)
        self.rect = pygame.Rect(TILE_SIZE, TILE_SIZE, TILE_SIZE - 10, TILE_SIZE - 10)
        self.speed = 4
        
        # Player attributes
        self.alive = True
        self.max_bombs = 1
        self.active_bombs = 0
        self.bomb_range = 2

    def update(self, joystick, walls, crates):
        if not self.alive:
            return

        # --- Axis Input Handling ---
        # Pygame normalizes evdev 0-255 absolute axes to a float between -1.0 and 1.0.
        # Your rules: 128 is center (0.0). < 64 is negative (-0.5). > 192 is positive (+0.5).
        axis_x = joystick.get_axis(0)
        axis_y = joystick.get_axis(1)

        dx, dy = 0, 0
        if axis_x < -0.5: dx = -self.speed
        if axis_x > 0.5:  dx = self.speed
        if axis_y < -0.5: dy = -self.speed
        if axis_y > 0.5:  dy = self.speed

        # Move X and check collision
        self.rect.x += dx
        self._collide(dx, 0, walls, crates)

        # Move Y and check collision
        self.rect.y += dy
        self._collide(0, dy, walls, crates)

    def _collide(self, dx, dy, walls, crates):
        obstacles = walls + [c['rect'] for c in crates]
        for obs in obstacles:
            if self.rect.colliderect(obs):
                if dx > 0: self.rect.right = obs.left
                if dx < 0: self.rect.left = obs.right
                if dy > 0: self.rect.bottom = obs.top
                if dy < 0: self.rect.top = obs.bottom

class Bomb:
    def __init__(self, x, y, owner):
        # Snap to grid
        self.grid_x = x // TILE_SIZE
        self.grid_y = y // TILE_SIZE
        self.rect = pygame.Rect(self.grid_x * TILE_SIZE, self.grid_y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        self.owner = owner
        self.place_time = time.time()
        self.duration = 3.0 # seconds until explosion

class Explosion:
    def __init__(self, rects):
        self.rects = rects
        self.spawn_time = time.time()
        self.duration = 0.5 # lingers for 0.5 seconds

class Game:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Gamepad-Server Bomberman")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 24)

        self.joysticks = {} # dict mapping instance_id -> pygame.joystick.Joystick
        self.players = {}   # dict mapping instance_id -> Player
        self.player_colors = [(255, 0, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
        
        self.walls = []
        self.crates = []
        self.bombs = []
        self.explosions = []
        
        self.generate_level()

    def generate_level(self):
        for y in range(ROWS):
            for x in range(COLS):
                rect = pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                # Outer borders and indestructible pillars (even x and y coords)
                if x == 0 or x == COLS - 1 or y == 0 or y == ROWS - 1 or (x % 2 == 0 and y % 2 == 0):
                    self.walls.append(rect)
                # Add random crates, leaving top left corner empty for spawn
                elif (x > 2 or y > 2) and x % 2 != 0:
                    self.crates.append({'rect': rect})

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # --- Hotplugging: Device Added ---
            elif event.type == pygame.JOYDEVICEADDED:
                joy = pygame.joystick.Joystick(event.device_index)
                joy.init()
                iid = joy.get_instance_id()
                self.joysticks[iid] = joy
                
                # Extract nickname from OS Hardware String
                raw_name = joy.get_name()
                if raw_name.startswith("Gamepad_"):
                    nickname = raw_name.replace("Gamepad_", "")
                else:
                    nickname = raw_name # Fallback
                
                color = self.player_colors[len(self.players) % len(self.player_colors)]
                self.players[iid] = Player(event.device_index, iid, nickname, color)
                print(f"[Engine] Player Joined: {nickname} (Virtual Device: {raw_name})")

            # --- Hotplugging: Device Removed ---
            elif event.type == pygame.JOYDEVICEREMOVED:
                iid = event.instance_id
                if iid in self.joysticks:
                    nickname = self.players[iid].nickname
                    del self.joysticks[iid]
                    del self.players[iid]
                    print(f"[Engine] Player Disconnected: {nickname}")

            # --- Action Buttons ---
            elif event.type == pygame.JOYBUTTONDOWN:
                iid = event.instance_id
                if iid in self.players:
                    player = self.players[iid]
                    if player.alive and event.button == BTN_A: # Button A pressed
                        if player.active_bombs < player.max_bombs:
                            # Place bomb centered on player
                            self.bombs.append(Bomb(player.rect.centerx, player.rect.centery, player))
                            player.active_bombs += 1

    def update(self):
        current_time = time.time()

        # Update Players
        for iid, player in self.players.items():
            if iid in self.joysticks:
                player.update(self.joysticks[iid], self.walls, self.crates)

        # Update Bombs
        active_bombs = []
        for bomb in self.bombs:
            if current_time - bomb.place_time >= bomb.duration:
                self.explode_bomb(bomb)
                bomb.owner.active_bombs -= 1
            else:
                active_bombs.append(bomb)
        self.bombs = active_bombs

        # Update Explosions & Hit Detection
        active_explosions = []
        for exp in self.explosions:
            if current_time - exp.spawn_time < exp.duration:
                active_explosions.append(exp)
                # Check for player deaths
                for p_id, player in self.players.items():
                    if player.alive and any(player.rect.colliderect(r) for r in exp.rects):
                        player.alive = False
                        print(f"[Engine] {player.nickname} was eliminated!")
            else:
                pass
        self.explosions = active_explosions

    def explode_bomb(self, bomb):
        explosion_rects = [bomb.rect]
        directions = [(1,0), (-1,0), (0,1), (0,-1)]
        
        for dx, dy in directions:
            for step in range(1, bomb.owner.bomb_range + 1):
                exp_x = bomb.grid_x + (dx * step)
                exp_y = bomb.grid_y + (dy * step)
                exp_rect = pygame.Rect(exp_x * TILE_SIZE, exp_y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                
                # Check walls
                if any(w.colliderect(exp_rect) for w in self.walls):
                    break # Stops explosion
                
                # Check crates
                hit_crate = False
                for crate in self.crates:
                    if crate['rect'].colliderect(exp_rect):
                        self.crates.remove(crate)
                        hit_crate = True
                        break
                
                explosion_rects.append(exp_rect)
                if hit_crate:
                    break # Crates stop explosion penetration

        self.explosions.append(Explosion(explosion_rects))

    def draw(self):
        self.screen.fill(BG_COLOR)

        # Draw Walls & Crates
        for wall in self.walls:
            pygame.draw.rect(self.screen, WALL_COLOR, wall)
        for crate in self.crates:
            pygame.draw.rect(self.screen, CRATE_COLOR, crate['rect'])

        # Draw Bombs
        for bomb in self.bombs:
            pygame.draw.circle(self.screen, BOMB_COLOR, bomb.rect.center, TILE_SIZE // 2 - 4)

        # Draw Explosions
        for exp in self.explosions:
            for r in exp.rects:
                pygame.draw.rect(self.screen, EXPLOSION_COLOR, r)

        # Draw Players & Nicknames
        for iid, player in self.players.items():
            if player.alive:
                pygame.draw.rect(self.screen, player.color, player.rect)
                # Draw Nickname
                name_surf = self.font.render(player.nickname, True, TEXT_COLOR)
                name_rect = name_surf.get_rect(center=(player.rect.centerx, player.rect.top - 10))
                self.screen.blit(name_surf, name_rect)

        pygame.display.flip()

    def run(self):
        while True:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)

if __name__ == "__main__":
    game = Game()
    game.run()
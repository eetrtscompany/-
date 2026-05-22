import math
import random
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass

import pygame

WIDTH, HEIGHT = 1280, 720
FPS = 60
UI_HEIGHT = 160
FIELD_RECT = pygame.Rect(0, 0, WIDTH, HEIGHT - UI_HEIGHT)
CORE_RECT = pygame.Rect(40, FIELD_RECT.centery - 80, 120, 160)
ALLY_SPAWN = (CORE_RECT.right + 40, CORE_RECT.centery)
ENEMY_MIN_X = WIDTH - 180
ENEMY_MAX_X = WIDTH - 20
ENEMY_MIN_Y = 40
ENEMY_MAX_Y = FIELD_RECT.bottom - 40
UNIT_COLLISION_RADIUS = 15

TYPE_ADV = {"Guard": "Shooter", "Shooter": "Floater", "Floater": "Guard"}
RESPAWN_TIME = {"Sentinel": 7.0, "Arcanist": 9.0, "Wisp": 11.0}

ALLY_DATA = {
    "Sentinel": dict(unit_type="Guard", cost=50, hp=120, attack=15, attack_range=45, attack_cooldown=0.8, move_speed=72),
    "Arcanist": dict(unit_type="Shooter", cost=80, hp=70, attack=20, attack_range=160, attack_cooldown=1.1, move_speed=54),
    "Wisp": dict(unit_type="Floater", cost=120, hp=90, attack=14, attack_range=120, attack_cooldown=1.5, move_speed=84),
}
ENEMY_DATA = {
    "Raider": dict(unit_type="Guard", hp=80, attack=10, attack_range=40, attack_cooldown=1.0, move_speed=60, reward=20, damage_to_core=5),
    "Imp Shooter": dict(unit_type="Shooter", hp=60, attack=12, attack_range=120, attack_cooldown=1.2, move_speed=48, reward=25, damage_to_core=5),
    "Drift Shade": dict(unit_type="Floater", hp=100, attack=14, attack_range=95, attack_cooldown=1.1, move_speed=72, reward=35, damage_to_core=8),
    "Heavy Brute": dict(unit_type="Guard", hp=250, attack=25, attack_range=42, attack_cooldown=1.3, move_speed=30, reward=60, damage_to_core=15),
}
WAVES = [
    {"Raider": 8}, {"Raider": 12, "Imp Shooter": 3}, {"Raider": 15, "Imp Shooter": 6}, {"Raider": 12, "Drift Shade": 5},
    {"Raider": 20, "Imp Shooter": 8, "Drift Shade": 4}, {"Heavy Brute": 2, "Raider": 15}, {"Heavy Brute": 3, "Imp Shooter": 10},
    {"Heavy Brute": 4, "Drift Shade": 8}, {"Raider": 25, "Imp Shooter": 15, "Drift Shade": 10},
    {"Heavy Brute": 8, "Raider": 20, "Imp Shooter": 15, "Drift Shade": 10},
]


def matchup_multiplier(attacker_type, defender_type):
    if TYPE_ADV[attacker_type] == defender_type:
        return 1.5
    if TYPE_ADV[defender_type] == attacker_type:
        return 0.75
    return 1.0




def load_girl_sprite_128():
    """Load requested girl image from local file if available, otherwise fallback pixel art."""
    for path in ("assets/girl_source.png", "assets/girl_source.jpg", "assets/girl_128.png"):
        if Path(path).exists():
            try:
                img = pygame.image.load(path).convert_alpha()
                return pygame.transform.scale(img, (128, 128))
            except Exception:
                pass
    surf = pygame.Surface((128, 128), pygame.SRCALPHA)
    # fallback: simple girl-like pixel sprite
    skin=(245,210,180); hair=(80,40,30); dress=(90,150,255); shade=(55,95,180)
    pygame.draw.rect(surf, hair, (36, 20, 56, 44))
    pygame.draw.rect(surf, skin, (44, 28, 40, 36))
    pygame.draw.rect(surf, hair, (40, 56, 48, 10))
    pygame.draw.rect(surf, dress, (40, 64, 48, 42))
    pygame.draw.rect(surf, shade, (46, 72, 36, 30))
    pygame.draw.rect(surf, skin, (28, 70, 12, 30))
    pygame.draw.rect(surf, skin, (88, 70, 12, 30))
    pygame.draw.rect(surf, skin, (48, 106, 12, 18))
    pygame.draw.rect(surf, skin, (68, 106, 12, 18))
    # pixelate look
    return pygame.transform.scale(pygame.transform.scale(surf, (32, 32)), (128, 128))
def create_pixel_sprite(unit_type, ally):
    scale = 3
    surf = pygame.Surface((8 * scale, 8 * scale), pygame.SRCALPHA)
    c1, c2 = ((90, 150, 255), (55, 95, 180)) if ally else ((240, 95, 95), (165, 60, 60))
    if unit_type == "Guard":
        pygame.draw.rect(surf, c1, (3, 3, 18, 18)); pygame.draw.rect(surf, c2, (6, 6, 12, 12))
    elif unit_type == "Shooter":
        pygame.draw.circle(surf, c1, (12, 12), 9); pygame.draw.circle(surf, c2, (12, 12), 6)
    else:
        pygame.draw.polygon(surf, c1, [(12, 0), (24, 21), (0, 21)]); pygame.draw.polygon(surf, c2, [(12, 6), (18, 18), (6, 18)])
    return surf


@dataclass
class FlashEffect:
    kind: str
    timer: float
    sx: float
    sy: float
    tx: float
    ty: float
    radius: float = 0
    def update(self, dt):
        self.timer -= dt
        return self.timer > 0


class Button:
    def __init__(self, rect, text, callback):
        self.rect = pygame.Rect(rect); self.text = text; self.callback = callback
    def draw(self, screen, font, selected=False):
        pygame.draw.rect(screen, (150, 120, 40) if selected else (70, 90, 140), self.rect, border_radius=6)
        pygame.draw.rect(screen, (20, 20, 30), self.rect, 2, border_radius=6)
        screen.blit(font.render(self.text, True, (230, 230, 230)), font.render(self.text, True, (230, 230, 230)).get_rect(center=self.rect.center))
    def click(self, pos):
        if self.rect.collidepoint(pos): self.callback(); return True
        return False


class Unit:
    def __init__(self, x, y, name, data, ally):
        self.name, self.unit_type, self.ally = name, data["unit_type"], ally
        self.max_hp = float(data["hp"]); self.hp = float(data["hp"])
        self.attack = float(data["attack"]); self.attack_range = float(data["attack_range"])
        self.attack_cooldown = float(data["attack_cooldown"]); self.move_speed = float(data["move_speed"])
        self.x, self.y = float(x), float(y)
        self.attack_timer = random.uniform(0, self.attack_cooldown * 0.5)
        self.level = 1; self.cost = data.get("cost", 0); self.upgrade_cost = int(self.cost * 0.8) if ally else 0
        self.reward = data.get("reward", 0); self.damage_to_core = data.get("damage_to_core", 0)
        self.sprite = create_pixel_sprite(self.unit_type, self.ally)
        if self.ally:
            base = load_girl_sprite_128()
            self.sprite = pygame.transform.scale(base, (36, 36))
        self.anim_t = random.random() * 10; self.is_moving = False; self.attack_flash = 0.0
        self.command_pos = None

    def alive(self): return self.hp > 0
    def dist_sq(self, other):
        dx, dy = other.x - self.x, other.y - self.y; return dx * dx + dy * dy
    def in_range(self, other): return self.dist_sq(other) <= self.attack_range * self.attack_range
    def move_towards(self, tx, ty, dt):
        dx, dy = tx - self.x, ty - self.y; d = math.hypot(dx, dy); self.is_moving = d > 1.0
        if d < 1e-5: return
        step = self.move_speed * dt
        self.x += dx / d * min(step, d); self.y += dy / d * min(step, d)
        self.x = max(10, min(WIDTH - 10, self.x)); self.y = max(10, min(FIELD_RECT.bottom - 10, self.y))
    def update_anim(self, dt): self.anim_t += dt; self.attack_flash = max(0.0, self.attack_flash - dt * 4)
    def draw(self, screen, selected=False):
        bob = math.sin(self.anim_t * 10) * (2 if self.is_moving else 0.5)
        screen.blit(self.sprite, self.sprite.get_rect(center=(int(self.x), int(self.y + bob))))
        if self.attack_flash > 0: pygame.draw.circle(screen, (255, 235, 120), (int(self.x), int(self.y)), 16, 2)
        if selected: pygame.draw.circle(screen, (255, 230, 80), (int(self.x), int(self.y)), 20, 2)
        w, ratio = 30, max(0.0, self.hp / self.max_hp)
        pygame.draw.rect(screen, (0, 0, 0), (int(self.x - w / 2), int(self.y - 24), w, 5))
        pygame.draw.rect(screen, (60, 220, 80), (int(self.x - w / 2), int(self.y - 24), int(w * ratio), 5))


class Projectile:
    def __init__(self, x, y, target, damage, unit_type, ally):
        self.x, self.y, self.target, self.damage, self.unit_type, self.ally, self.speed, self.alive = x, y, target, damage, unit_type, ally, 300, True
    def update(self, dt, scene):
        if not self.target or not self.target.alive(): self.alive = False; return
        dx, dy = self.target.x - self.x, self.target.y - self.y; d = math.hypot(dx, dy)
        if d < 8:
            scene.apply_attack_damage(self.unit_type, self.damage, self.target, self.ally); self.target.attack_flash = 0.7; self.alive = False; return
        step = self.speed * dt; self.x += dx / d * min(step, d); self.y += dy / d * min(step, d)
    def draw(self, screen): pygame.draw.circle(screen, (240, 220, 120), (int(self.x), int(self.y)), 4)


class WaveManager:
    def __init__(self):
        self.wave_index = -1; self.in_prep = True; self.prep_timer = 2.0; self.spawn_timer = 0.0; self.queue = []; self.finished = False
    def start_next(self):
        self.wave_index += 1
        if self.wave_index >= len(WAVES): self.finished = True; return
        self.queue = []
        for name, c in WAVES[self.wave_index].items(): self.queue += [name] * c
        random.shuffle(self.queue); self.spawn_timer = 0.7; self.in_prep = False
    def update(self, dt, scene):
        if self.finished: return
        if self.in_prep:
            self.prep_timer -= dt
            if self.prep_timer <= 0: self.start_next()
            return
        self.spawn_timer -= dt
        if self.queue and self.spawn_timer <= 0: scene.spawn_enemy(self.queue.pop()); self.spawn_timer = 0.6
        if not self.queue and not scene.enemies: self.in_prep = True; self.prep_timer = 5.0


class BattleScene:
    def __init__(self, manager):
        self.manager = manager
        self.font = pygame.font.SysFont(None, 28); self.small = pygame.font.SysFont(None, 22)
        self.money = 200; self.core_hp = 100; self.game_over = False; self.victory = False; self.paused = False
        self.selected_purchase = None; self.selected_allies = []; self.inspected_enemy = None
        self.drag_select_start = None; self.drag_select_current = None
        self.allies, self.enemies, self.projectiles, self.effects = [], [], [], []
        self.respawn_queues = defaultdict(list)
        self.wave = WaveManager(); self.buttons = []; self._build_ui()

    def _build_ui(self):
        y = HEIGHT - UI_HEIGHT + 80
        self.buttons = [Button((20, y, 140, 40), "1 Sentinel", lambda: self.select_purchase("Sentinel")), Button((170, y, 140, 40), "2 Arcanist", lambda: self.select_purchase("Arcanist")), Button((320, y, 140, 40), "3 Wisp", lambda: self.select_purchase("Wisp")), Button((490, y, 140, 40), "Upgrade", self.try_upgrade_selected), Button((640, y, 140, 40), "Pause", self.toggle_pause)]

    def select_purchase(self, name): self.selected_purchase = name; self.selected_allies.clear()
    def toggle_pause(self): self.paused = not self.paused

    def try_upgrade_selected(self):
        for u in list(self.selected_allies):
            if u not in self.allies or u.level >= 5 or self.money < u.upgrade_cost: continue
            self.money -= u.upgrade_cost; old = u.max_hp
            u.level += 1; u.max_hp *= 1.2; u.hp += (u.max_hp - old); u.attack *= 1.2; u.attack_cooldown *= 0.95; u.upgrade_cost = int(u.upgrade_cost * 1.6)

    def spawn_enemy(self, name):
        self.enemies.append(Unit(random.randint(ENEMY_MIN_X, ENEMY_MAX_X), random.randint(ENEMY_MIN_Y, ENEMY_MAX_Y), name, ENEMY_DATA[name], False))

    def valid_place(self, x, y):
        if y >= FIELD_RECT.bottom - 5 or CORE_RECT.inflate(70, 70).collidepoint(x, y) or x > WIDTH - 200: return False
        for a in self.allies:
            if math.hypot(a.x - x, a.y - y) < 28: return False
        return FIELD_RECT.collidepoint(x, y)

    def place_ally(self, x, y):
        if not self.selected_purchase: return
        d = ALLY_DATA[self.selected_purchase]
        if self.money < d["cost"] or not self.valid_place(x, y): return
        self.money -= d["cost"]
        u = Unit(ALLY_SPAWN[0], ALLY_SPAWN[1], self.selected_purchase, d, True)
        u.command_pos = (x, y)
        self.allies.append(u)
        self.selected_purchase = None

    def enqueue_respawn(self, ally):
        self.respawn_queues[ally.name].append({
            "name": ally.name,
            "level": ally.level,
            "upgrade_cost": ally.upgrade_cost,
            "max_hp": ally.max_hp,
            "attack": ally.attack,
            "attack_cooldown": ally.attack_cooldown,
            "command_pos": ally.command_pos,
            "timer": RESPAWN_TIME[ally.name],
        })

    def update_respawns(self, dt):
        for name, queue in self.respawn_queues.items():
            if not queue:
                continue
            queue[0]["timer"] -= dt
            if queue[0]["timer"] <= 0:
                info = queue.pop(0)
                u = Unit(ALLY_SPAWN[0], ALLY_SPAWN[1], info["name"], ALLY_DATA[info["name"]], True)
                u.level = info["level"]; u.upgrade_cost = info["upgrade_cost"]; u.max_hp = info["max_hp"]; u.hp = info["max_hp"]
                u.attack = info["attack"]; u.attack_cooldown = info["attack_cooldown"]; u.command_pos = info["command_pos"]
                self.allies.append(u)

    def apply_attack_damage(self, attacker_type, base_damage, target, attacker_is_ally):
        target.hp -= base_damage * matchup_multiplier(attacker_type, target.unit_type); target.attack_flash = 0.8
        if target.hp <= 0 and not target.ally and attacker_is_ally: self.money += target.reward

    def move_with_separation(self, dt):
        for ally in self.allies:
            if ally.command_pos:
                if math.hypot(ally.command_pos[0] - ally.x, ally.command_pos[1] - ally.y) > 5:
                    ally.move_towards(ally.command_pos[0], ally.command_pos[1], dt)
                else:
                    ally.is_moving = False
            else:
                ally.is_moving = False
        for i, a in enumerate(self.allies):
            for b in self.allies[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                min_d = UNIT_COLLISION_RADIUS * 2
                if 0 < d < min_d:
                    push = (min_d - d) * 0.5
                    nx, ny = dx / d, dy / d
                    a.x -= nx * push; a.y -= ny * push
                    b.x += nx * push; b.y += ny * push

    def update_units(self, dt):
        self.move_with_separation(dt)
        for ally in list(self.allies):
            near = [e for e in self.enemies if ally.in_range(e)]
            if not near:
                continue
            target = min(near, key=lambda e: ally.dist_sq(e))
            ally.attack_timer -= dt
            if ally.attack_timer <= 0:
                ally.attack_timer = ally.attack_cooldown; ally.attack_flash = 1.0
                if ally.unit_type == "Shooter": self.projectiles.append(Projectile(ally.x, ally.y, target, ally.attack, ally.unit_type, True))
                else:
                    self.apply_attack_damage(ally.unit_type, ally.attack, target, True)
                    self.effects.append(FlashEffect("line", 0.08, ally.x, ally.y, target.x, target.y))
                    if ally.unit_type == "Floater":
                        self.effects.append(FlashEffect("aoe", 0.12, 0, 0, target.x, target.y, 50))
                        for e in self.enemies:
                            if e is not target and math.hypot(e.x - target.x, e.y - target.y) <= 50:
                                self.apply_attack_damage(ally.unit_type, ally.attack * 0.5, e, True)

        for enemy in list(self.enemies):
            enemy.attack_timer -= dt
            near = [a for a in self.allies if enemy.in_range(a)]
            if near:
                target = min(near, key=lambda a: enemy.dist_sq(a))
                if enemy.attack_timer <= 0:
                    enemy.attack_timer = enemy.attack_cooldown; enemy.attack_flash = 1.0
                    self.apply_attack_damage(enemy.unit_type, enemy.attack, target, False)
                    self.effects.append(FlashEffect("line", 0.07, enemy.x, enemy.y, target.x, target.y))
            else:
                enemy.move_towards(CORE_RECT.centerx, CORE_RECT.centery, dt)
                if CORE_RECT.collidepoint(enemy.x, enemy.y): self.core_hp -= enemy.damage_to_core; enemy.hp = 0

        alive_allies = []
        for a in self.allies:
            if a.alive(): alive_allies.append(a)
            else: self.enqueue_respawn(a)
        self.allies = alive_allies
        self.enemies = [e for e in self.enemies if e.alive()]
        self.selected_allies = [a for a in self.selected_allies if a in self.allies]
        if self.inspected_enemy and self.inspected_enemy not in self.enemies: self.inspected_enemy = None

    def find_ally_at(self, pos):
        for a in self.allies:
            if math.hypot(a.x - pos[0], a.y - pos[1]) <= 18: return a
        return None
    def find_enemy_at(self, pos):
        for e in self.enemies:
            if math.hypot(e.x - pos[0], e.y - pos[1]) <= 18: return e
        return None
    def get_additive_mod(self):
        m = pygame.key.get_mods(); return bool(m & pygame.KMOD_CTRL or m & pygame.KMOD_ALT)

    def command_selected_move(self, pos):
        if not self.selected_allies:
            return
        cols = max(1, int(math.sqrt(len(self.selected_allies))))
        spacing = UNIT_COLLISION_RADIUS * 2 + 4
        for i, u in enumerate(self.selected_allies):
            row, col = divmod(i, cols)
            ox = (col - (cols - 1) / 2) * spacing
            oy = row * spacing
            u.command_pos = (pos[0] + ox, pos[1] + oy)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE: self.manager.set_scene(TitleScene(self.manager))
            if event.key == pygame.K_SPACE: self.toggle_pause()
            if event.key == pygame.K_1: self.select_purchase("Sentinel")
            if event.key == pygame.K_2: self.select_purchase("Arcanist")
            if event.key == pygame.K_3: self.select_purchase("Wisp")
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for b in self.buttons:
                if b.click(event.pos): return
            if FIELD_RECT.collidepoint(event.pos): self.drag_select_start = event.pos; self.drag_select_current = event.pos
        if event.type == pygame.MOUSEMOTION and self.drag_select_start: self.drag_select_current = event.pos
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self.drag_select_start: return
            start, end = self.drag_select_start, event.pos
            self.drag_select_start = None; self.drag_select_current = None
            additive = self.get_additive_mod()
            rect = pygame.Rect(min(start[0], end[0]), min(start[1], end[1]), abs(end[0] - start[0]), abs(end[1] - start[1]))
            if rect.width < 6 and rect.height < 6:
                ally, enemy = self.find_ally_at(end), self.find_enemy_at(end)
                if ally:
                    if not additive: self.selected_allies.clear()
                    if ally not in self.selected_allies: self.selected_allies.append(ally)
                    self.selected_purchase = None; self.inspected_enemy = None
                elif enemy:
                    if not additive: self.selected_allies.clear()
                    self.inspected_enemy = enemy; self.selected_purchase = None
                else:
                    if self.selected_purchase: self.place_ally(*end)
                    elif not additive: self.selected_allies.clear(); self.inspected_enemy = None
            else:
                if not additive: self.selected_allies.clear()
                for ally in self.allies:
                    if rect.collidepoint(ally.x, ally.y) and ally not in self.selected_allies: self.selected_allies.append(ally)
                self.selected_purchase = None; self.inspected_enemy = None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            if FIELD_RECT.collidepoint(event.pos) and self.selected_allies:
                self.command_selected_move(event.pos)
            else:
                self.selected_purchase = None; self.selected_allies.clear(); self.inspected_enemy = None

    def update(self, dt):
        for u in self.allies + self.enemies: u.update_anim(dt)
        self.update_respawns(dt)
        if self.game_over or self.victory or self.paused: return
        self.wave.update(dt, self); self.update_units(dt)
        for p in list(self.projectiles): p.update(dt, self)
        self.projectiles = [p for p in self.projectiles if p.alive]
        self.effects = [e for e in self.effects if e.update(dt)]
        if self.core_hp <= 0: self.game_over = True
        if self.wave.finished and not self.enemies: self.victory = True

    def draw(self, screen):
        screen.fill((25, 30, 42)); pygame.draw.rect(screen, (38, 48, 66), FIELD_RECT); pygame.draw.rect(screen, (55, 90, 140), CORE_RECT)
        screen.blit(self.small.render("Archive Core", True, (240, 240, 255)), (CORE_RECT.x + 5, CORE_RECT.y - 24))
        for u in self.allies: u.draw(screen, selected=(u in self.selected_allies))
        for e in self.enemies: e.draw(screen)
        for p in self.projectiles: p.draw(screen)
        for ef in self.effects:
            if ef.kind == "line": pygame.draw.line(screen, (245, 235, 130), (ef.sx, ef.sy), (ef.tx, ef.ty), 2)
            else:
                s = pygame.Surface((ef.radius * 2, ef.radius * 2), pygame.SRCALPHA)
                pygame.draw.circle(s, (180, 200, 255, 70), (ef.radius, ef.radius), ef.radius)
                screen.blit(s, (ef.tx - ef.radius, ef.ty - ef.radius))
        if self.drag_select_start and self.drag_select_current:
            rect = pygame.Rect(min(self.drag_select_start[0], self.drag_select_current[0]), min(self.drag_select_start[1], self.drag_select_current[1]), abs(self.drag_select_current[0] - self.drag_select_start[0]), abs(self.drag_select_current[1] - self.drag_select_start[1]))
            pygame.draw.rect(screen, (255, 255, 120), rect, 1)

        pygame.draw.rect(screen, (18, 18, 25), (0, HEIGHT - UI_HEIGHT, WIDTH, UI_HEIGHT))
        status = f"Money:{self.money} Core:{max(0, int(self.core_hp))} Wave:{min(self.wave.wave_index+1, len(WAVES))}/{len(WAVES)}"
        if self.wave.in_prep and not self.wave.finished: status += f" Prep:{max(0, self.wave.prep_timer):.1f}s"
        screen.blit(self.font.render(status, True, (240, 240, 240)), (20, HEIGHT - UI_HEIGHT + 20))
        for b in self.buttons: b.draw(screen, self.small, selected=(self.selected_purchase and self.selected_purchase in b.text))
        respawn_txt = "Respawn " + " ".join([f"{k}:{q[0]['timer']:.1f}s" for k, q in self.respawn_queues.items() if q])
        screen.blit(self.small.render(respawn_txt, True, (200, 200, 210)), (820, HEIGHT - UI_HEIGHT + 24))
        info = f"Selected Allies:{len(self.selected_allies)}  (RightClick: move command)"
        if self.selected_purchase:
            d = ALLY_DATA[self.selected_purchase]; info = f"Place {self.selected_purchase} Cost:{d['cost']} Type:{d['unit_type']}"
        screen.blit(self.small.render(info, True, (210, 210, 220)), (20, HEIGHT - 35))
        if self.inspected_enemy:
            e = self.inspected_enemy; box = pygame.Rect(WIDTH - 305, 15, 290, 130)
            pygame.draw.rect(screen, (18, 18, 25), box, border_radius=6); pygame.draw.rect(screen, (130, 130, 150), box, 1, border_radius=6)
            lines = [f"Enemy:{e.name}", f"Type:{e.unit_type}", f"HP:{int(max(0,e.hp))}/{int(e.max_hp)}", f"ATK:{int(e.attack)} SPD:{e.move_speed:.0f}", f"Reward:{e.reward}"]
            for i, line in enumerate(lines): screen.blit(self.small.render(line, True, (230, 230, 240)), (box.x + 10, box.y + 8 + i * 22))
        if self.paused: screen.blit(self.font.render("PAUSED", True, (255, 220, 80)), (WIDTH // 2 - 50, 20))
        if self.game_over: screen.blit(self.font.render("GAME OVER - ESC:Title", True, (255, 120, 120)), (WIDTH // 2 - 140, 20))
        if self.victory: screen.blit(self.font.render("VICTORY! - ESC:Title", True, (130, 255, 150)), (WIDTH // 2 - 120, 20))


class TitleScene:
    def __init__(self, manager): self.manager = manager; self.font = pygame.font.SysFont(None, 74); self.small = pygame.font.SysFont(None, 34)
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE): self.manager.set_scene(BattleScene(self.manager))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: self.manager.set_scene(BattleScene(self.manager))
    def update(self, dt): _ = dt
    def draw(self, screen):
        screen.fill((18, 22, 36)); screen.blit(self.font.render("Archive Guardian", True, (220, 230, 255)), (330, 220)); screen.blit(self.small.render("Press Enter/Space/Click to Start", True, (220, 220, 220)), (430, 350))


class SceneManager:
    def __init__(self): self.scene = TitleScene(self)
    def set_scene(self, scene): self.scene = scene


class Game:
    def __init__(self):
        pygame.init(); pygame.display.set_caption("Archive Guardian"); self.screen = pygame.display.set_mode((WIDTH, HEIGHT)); self.clock = pygame.time.Clock(); self.running = True; self.manager = SceneManager()
    def run(self):
        try:
            while self.running:
                dt = self.clock.tick(FPS) / 1000.0
                for event in pygame.event.get():
                    if event.type == pygame.QUIT: self.running = False
                    else: self.manager.scene.handle_event(event)
                self.manager.scene.update(dt); self.manager.scene.draw(self.screen); pygame.display.flip()
        except Exception:
            print("Runtime error:", file=sys.stderr); traceback.print_exc()
        finally:
            pygame.quit()


if __name__ == "__main__":
    Game().run()

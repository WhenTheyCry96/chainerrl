import collections
import os
import sys

import numpy as np
import scipy.misc as spm
from ale_python_interface import ALEInterface
from PIL import Image
import cv2

import environment


class ALE(environment.EpisodicEnvironment):
    """Arcade Learning Environment.
    """

    def __init__(self, rom_filename, seed=0, use_sdl=False, n_last_screens=4,
                 frame_skip=4, treat_life_lost_as_terminal=True, crop_or_scale='scale'):
        self.n_last_screens = n_last_screens
        self.treat_life_lost_as_terminal = treat_life_lost_as_terminal
        self.crop_or_scale = crop_or_scale

        ale = ALEInterface()
        ale.setInt(b'random_seed', seed)
        self.frame_skip = frame_skip
        if use_sdl:
            if 'DISPLAY' not in os.environ:
                raise RuntimeError(
                    'Please set DISPLAY environment variable for use_sdl=True')
            # SDL settings below are from the ALE python example
            if sys.platform == 'darwin':
                import pygame
                pygame.init()
                ale.setBool('sound', False)  # Sound doesn't work on OSX
            elif sys.platform.startswith('linux'):
                ale.setBool('sound', True)
            ale.setBool('display_screen', True)
        ale.loadROM(str.encode(rom_filename))

        assert ale.getFrameNumber() == 0

        self.ale = ale
        self.legal_actions = ale.getMinimalActionSet()
        self.initialize()

    def current_screen(self):
        # Max of two consecutive frames
        rgb_img = np.maximum(self.ale.getScreenRGB(), self.last_raw_screen)
        assert rgb_img.shape == (210, 160, 3)
        # RGB -> Luminance
        img = rgb_img[:, :, 0] * 0.2126 + rgb_img[:, :, 1] * \
            0.0722 + rgb_img[:, :, 2] * 0.7152
        if img.shape == (250, 160):
            raise RuntimeError("This ROM is for PAL. Please use ROMs for NTSC")
        assert img.shape == (210, 160)
        if self.crop_or_scale == 'crop':
            # Shrink (210, 160) -> (110, 84)
            img = cv2.resize(img, (84, 110),
                             interpolation=cv2.INTER_LINEAR)
            img = img.astype(np.float32)
            assert img.shape == (110, 84)
            # Crop (110, 84) -> (84, 84)
            unused_height = 110 - 84
            bottom_crop = 8
            top_crop = unused_height - bottom_crop
            img = img[top_crop: 110 - bottom_crop, :]
        elif self.crop_or_scale == 'scale':
            img = cv2.resize(img, (84, 84),
                             interpolation=cv2.INTER_LINEAR)
            img = img.astype(np.float32)
        else:
            raise RuntimeError('crop_or_scale must be either crop or scale')
        assert img.shape == (84, 84)
        # [0,255] -> [-128, 127]
        img -= 128
        # [-128, 127] -> [-1, 1)
        img /= 128.0
        return img

    @property
    def state(self):
        ret = np.asarray(self.last_screens)
        assert ret.shape == (4, 84, 84)
        return ret

    @property
    def is_terminal(self):
        if self.treat_life_lost_as_terminal:
            return self.lives_lost or self.ale.game_over()
        else:
            return self.ale.game_over()

    @property
    def reward(self):
        return self._reward

    @property
    def number_of_actions(self):
        return len(self.legal_actions)

    def receive_action(self, action):
        assert not self.is_terminal

        raw_reward = 0
        for i in xrange(4):

            # Last screeen must be stored before executing the 4th action
            if i == 3:
                self.last_raw_screen = self.ale.getScreenRGB()

            raw_reward += self.ale.act(self.legal_actions[action])

            # Check if lives are lost
            if self.lives > self.ale.lives():
                self.lives_lost = True
            else:
                self.lives_lost = False
            self.lives = self.ale.lives()

            if self.is_terminal:
                break

        # We must have last screen here unless it's terminal
        self.last_screens.append(self.current_screen())

        if raw_reward > 0:
            self._reward = 1
        elif raw_reward < 0:
            self._reward = -1
        else:
            self._reward = 0
        return self._reward

    def initialize(self):

        if self.ale.game_over():
            self.ale.reset_game()

        self._reward = 0

        self.last_raw_screen = self.ale.getScreenRGB()

        self.last_screens = collections.deque(
            [self.current_screen()] * self.n_last_screens,
            maxlen=self.n_last_screens)

        self.lives_lost = False
        self.lives = self.ale.lives()

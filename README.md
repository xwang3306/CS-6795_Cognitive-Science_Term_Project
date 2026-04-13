# CS-6795 Cognitive Science Term Project

This repository contains the code, data processing pipeline, and paper materials for my CS-6795 Cognitive Science term project at Georgia Tech.

## Project Overview

This project studies cognitive burden in **Werewolf** (狼人杀), a multi-player social deduction game with hidden information, asymmetric roles, public argumentation, and strategic deception. THe games were played in Chinese.

The main goal is to develop a **turn-level behavioral framework** for analyzing how different forms of cognitive burden arise during gameplay. Rather than treating burden as a single general construct, the project proposes three role- and interaction-sensitive measures:

- **role-coherence pressure**: the burden of maintaining a coherent role-consistent narrative
- **self-repair pressure**: the burden of explaining, correcting, or defending one's prior stance
- **public disagreement load**: the level of conflict in the shared public interaction space

Using game transcripts, the pipeline reconstructs turn-level interactional structure, annotates stance, and computes burden-related measures for exploratory analysis.

## Research Questions

This project is organized around three questions:

1. What kinds of cognitive burden arise in social deduction dialogue, and how can these burdens be conceptually distinguished?
2. How can these forms of burden be operationalized at the level of individual speech turns using game-state structure, stance information, and role-specific private knowledge?
3. Do the resulting measures show meaningful differences across player roles, interactional situations, and high-pressure moments within the game?

## Repository Structure

```text
.
├── data/               # Raw and processed game data
├── Code/               # Data processing and analysis scripts

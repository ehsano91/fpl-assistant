export type Position = "GK" | "DEF" | "MID" | "FWD";
export type FitnessStatus = "fit" | "doubt" | "out";
export type RecType = "transfer_in" | "transfer_out" | "captain" | "starting_xi" | "chip_alert";

export interface Player {
  id: number;
  name: string;
  shortName: string;
  position: Position;
  team: string;
  xP: number;
  xPForecast: number[];
  isCaptain: boolean;
  isViceCaptain: boolean;
  fitness: FitnessStatus;
}

export interface Recommendation {
  id: number;
  type: RecType;
  title: string;
  summary: string;
  reasoning: string;
  positive: boolean;
}

export interface NewsPill {
  player: string;
  status: "injury" | "returning" | "suspended" | "flagged";
  text: string;
}

export const myTeam: Player[] = [
  { id: 1, name: "Alisson Becker", shortName: "Alisson", position: "GK", team: "LIV", xP: 4.2, xPForecast: [4.2, 3.8, 4.5, 4.1, 3.9, 4.3], isCaptain: false, isViceCaptain: false, fitness: "fit" },
  { id: 2, name: "Virgil van Dijk", shortName: "Van Dijk", position: "DEF", team: "LIV", xP: 5.8, xPForecast: [5.8, 5.2, 6.3, 5.5, 6.0, 5.4], isCaptain: false, isViceCaptain: false, fitness: "fit" },
  { id: 3, name: "William Saliba", shortName: "Saliba", position: "DEF", team: "ARS", xP: 5.3, xPForecast: [5.3, 5.0, 4.8, 5.5, 5.1, 4.9], isCaptain: false, isViceCaptain: false, fitness: "fit" },
  { id: 4, name: "Josko Gvardiol", shortName: "Gvardiol", position: "DEF", team: "MCI", xP: 4.8, xPForecast: [4.8, 4.2, 5.1, 4.6, 4.9, 4.4], isCaptain: false, isViceCaptain: false, fitness: "doubt" },
  { id: 5, name: "Gabriel Magalhães", shortName: "Gabriel", position: "DEF", team: "ARS", xP: 4.5, xPForecast: [4.5, 4.1, 4.9, 4.3, 4.7, 4.2], isCaptain: false, isViceCaptain: false, fitness: "fit" },
  { id: 6, name: "Mohamed Salah", shortName: "Salah", position: "MID", team: "LIV", xP: 8.7, xPForecast: [8.7, 7.9, 9.2, 8.1, 8.5, 7.8], isCaptain: true, isViceCaptain: false, fitness: "fit" },
  { id: 7, name: "Bukayo Saka", shortName: "Saka", position: "MID", team: "ARS", xP: 7.2, xPForecast: [7.2, 6.8, 7.5, 6.9, 7.1, 6.5], isCaptain: false, isViceCaptain: true, fitness: "fit" },
  { id: 8, name: "Cole Palmer", shortName: "Palmer", position: "MID", team: "CHE", xP: 7.8, xPForecast: [7.8, 7.1, 8.3, 7.4, 7.9, 7.2], isCaptain: false, isViceCaptain: false, fitness: "fit" },
  { id: 9, name: "Martin Ødegaard", shortName: "Ødegaard", position: "MID", team: "ARS", xP: 5.9, xPForecast: [5.9, 5.5, 6.2, 5.7, 6.0, 5.3], isCaptain: false, isViceCaptain: false, fitness: "out" },
  { id: 10, name: "Erling Haaland", shortName: "Haaland", position: "FWD", team: "MCI", xP: 8.1, xPForecast: [8.1, 7.5, 8.8, 7.9, 8.3, 7.6], isCaptain: false, isViceCaptain: false, fitness: "fit" },
  { id: 11, name: "Alexander Isak", shortName: "Isak", position: "FWD", team: "LIV", xP: 6.9, xPForecast: [6.9, 6.3, 7.4, 6.7, 7.0, 6.1], isCaptain: false, isViceCaptain: false, fitness: "out" },
];

export const bench: Player[] = [
  { id: 12, name: "Robert Sánchez", shortName: "Sánchez", position: "GK", team: "CHE", xP: 3.5, xPForecast: [3.5, 3.2, 3.8, 3.4, 3.6, 3.1], isCaptain: false, isViceCaptain: false, fitness: "fit" },
  { id: 13, name: "Ezri Konsa", shortName: "Konsa", position: "DEF", team: "AVL", xP: 3.9, xPForecast: [3.9, 3.5, 4.2, 3.7, 4.0, 3.4], isCaptain: false, isViceCaptain: false, fitness: "fit" },
  { id: 14, name: "Emile Smith Rowe", shortName: "Smith Rowe", position: "MID", team: "FUL", xP: 3.2, xPForecast: [3.2, 2.9, 3.6, 3.0, 3.3, 2.8], isCaptain: false, isViceCaptain: false, fitness: "doubt" },
  { id: 15, name: "Dominic Solanke", shortName: "Solanke", position: "FWD", team: "TOT", xP: 4.1, xPForecast: [4.1, 3.7, 4.5, 3.9, 4.2, 3.6], isCaptain: false, isViceCaptain: false, fitness: "fit" },
];

export const recommendations: Recommendation[] = [
  { id: 1, type: "transfer_in", title: "Transfer In: Jarrod Bowen", summary: "Strong upcoming fixtures (WHU vs. NFO, BOU, IPS). High xG involvement.", positive: true, reasoning: "Bowen has 3 goals and 2 assists in his last 5 matches. West Ham face three bottom-half teams in the next 3 GWs. His xGI per 90 of 0.72 ranks in the top 10% of midfielders this season." },
  { id: 2, type: "transfer_out", title: "Transfer Out: Ødegaard", summary: "Flagged as injured. Expected to miss 2-3 GWs.", positive: false, reasoning: "Ødegaard sustained a knee ligament issue in training. Arsenal's medical staff estimates 2-3 weeks recovery. With tough fixtures ahead (MCI, LIV), his replacement could fund a premium option." },
  { id: 3, type: "captain", title: "Captain Pick: Salah (C)", summary: "Liverpool face Bournemouth (H). Salah has 4 goals in last 3 home games.", positive: true, reasoning: "Salah's home record this season is exceptional: 0.92 xGI per 90. Bournemouth have conceded the 3rd most goals away from home. Historical data shows Salah averages 9.3 pts in equivalent fixtures." },
  { id: 4, type: "chip_alert", title: "Consider: Triple Captain GW24", summary: "Double gameweek confirmed for Liverpool. Salah could be a TC target.", positive: true, reasoning: "Liverpool have a confirmed DGW24 with fixtures vs BOU (H) and WOL (A). Salah's DGW expected points of 16.4 make this the best TC opportunity of the season so far." },
  { id: 5, type: "starting_xi", title: "Bench: Gvardiol (75% chance)", summary: "Gvardiol flagged with a minor knock. Consider benching.", positive: false, reasoning: "Pep's press conference mentioned Gvardiol as 'uncertain'. With a 75% fitness rating, there's a 25% chance of a 1-point cameo. Your bench options provide safer floor points." },
];

export const newsPills: NewsPill[] = [
  { player: "Ødegaard", status: "injury", text: "Knee — 2-3 wks" },
  { player: "Gvardiol", status: "flagged", text: "Minor knock — 75%" },
  { player: "Rashford", status: "returning", text: "Back in training" },
  { player: "Stones", status: "injury", text: "Hamstring — 4 wks" },
  { player: "Richarlison", status: "suspended", text: "Red card ban" },
  { player: "Mount", status: "returning", text: "Fit for GW24" },
];

export const briefingSummary = `GW23 is shaping up to be pivotal. Liverpool's home fixture against Bournemouth makes Salah the standout captaincy option with an xP of 8.7. Key concern: Ødegaard's knee injury means you'll need a midfield replacement — Bowen (WHU) and Mbeumo (BRE) are the top picks based on fixture difficulty and form. Watch Gvardiol's fitness closely before the deadline. If he's ruled out, Gabriel or a budget enabler like Mykolenko could plug the gap. The free hit chip may be worth saving for the blank GW26.`;

export const dataSources = [
  { name: "FPL Official API", status: "ok" as const, lastUpdate: "2 mins ago" },
  { name: "Understat xG Data", status: "ok" as const, lastUpdate: "15 mins ago" },
  { name: "Injury Tracker", status: "ok" as const, lastUpdate: "1 hr ago" },
  { name: "Fixture Difficulty", status: "ok" as const, lastUpdate: "3 hrs ago" },
  { name: "Press Conference NLP", status: "warning" as const, lastUpdate: "6 hrs ago" },
];

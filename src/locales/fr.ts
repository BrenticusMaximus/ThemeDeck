/**
 * French translations, keyed by the English source string.
 *
 * - Keys must match the English text passed to `t()` exactly.
 * - `{name}` placeholders are replaced at runtime by `t("…", { name })`.
 * - Untranslated or new strings automatically fall back to English.
 * - Register: vouvoiement.
 * - Typography: French spacing uses non-breaking spaces (\u00A0).
 */
export const fr: Record<string, string> = {
  // --- Shared actions -------------------------------------------------------
  "Remove": "Retirer",
  "Done": "Terminé",
  "Back": "Retour",
  "Cancel": "Annuler",
  "Play": "Lire",
  "Pause": "Pause",
  "Mute": "Couper le son",
  "Up": "Monter",
  "Download": "Télécharger",
  "Download & Add": "Télécharger et ajouter",
  "Downloading...": "Téléchargement…",
  "Loading...": "Chargement…",
  "Searching...": "Recherche…",
  "Installing...": "Installation…",
  "Updating...": "Mise à jour…",

  // --- Track and game names ------------------------------------------------
  "Global ambient music": "Musique ambiante globale",
  "Ambient music": "Musique ambiante",
  "Store music": "Musique de la boutique",
  "Global track": "Piste globale",
  "Unknown game": "Jeu inconnu",
  "Unknown album": "Album inconnu",
  "Unknown track": "Piste inconnue",
  "Name unavailable": "Nom indisponible",
  "No audio data returned": "Aucune donnée audio renvoyée",
  "No preview audio returned": "Aucun aperçu audio renvoyé",

  // --- Now playing card -----------------------------------------------------
  "NOW PLAYING": "LECTURE EN COURS",
  "PAUSED": "EN PAUSE",
  "Previous track": "Piste précédente",
  "Next track": "Piste suivante",
  "Play music": "Lire la musique",
  "Pause music": "Mettre la musique en pause",
  "Choose ThemeDeck music": "Choisir la musique ThemeDeck",
  "Choose ThemeDeck music...": "Choisir la musique ThemeDeck…",
  "Time remaining": "Temps restant",
  "Now playing card anchor": "Ancrage de la fiche Lecture en cours",
  "Choose where the card starts before fine-tuning offsets.":
    "Choisissez le point de départ de la fiche avant d’ajuster les décalages.",
  "Top left": "En haut à gauche",
  "Top right": "En haut à droite",
  "Bottom left": "En bas à gauche",
  "Bottom right": "En bas à droite",
  "Horizontal offset": "Décalage horizontal",
  "Vertical offset": "Décalage vertical",
  "Card max width": "Largeur maximale de la fiche",
  "Show game-page now playing card": "Afficher la fiche Lecture en cours sur la page du jeu",
  "Displays artist/track while game music is playing.":
    "Affiche l’artiste et la piste pendant la lecture de la musique du jeu.",

  // --- Plugin panel ---------------------------------------------------------
  "Latest change:": "Dernière modification\u00A0:",
  "Build ID:": "ID de version\u00A0:",
  "To assign music tracks, go to a game's page, select the \"gear\" icon, then \"Choose ThemeDeck music...\"":
    "Pour assigner des pistes, ouvrez la page d’un jeu, sélectionnez l’icône «\u00A0engrenage\u00A0», puis «\u00A0Choisir la musique ThemeDeck…\u00A0».",
  "Auto play on game page": "Lecture automatique sur la page du jeu",
  "Start music as soon as you open a game's details view.":
    "Démarre la musique dès l’ouverture de la fiche d’un jeu.",
  "Stop music after pressing Play": "Arrêter la musique après avoir appuyé sur Jouer",
  "Choose when ThemeDeck music should stop during game launch:":
    "Choisissez quand la musique ThemeDeck doit s’arrêter au lancement du jeu\u00A0:",
  "Stop music timing on launch": "Moment d’arrêt de la musique au lancement",
  "At launch start": "Au début du lancement",
  "At launch finish": "À la fin du lancement",
  "Allow music while games/apps run in the background":
    "Autoriser la musique lorsqu’un jeu ou une application tourne en arrière-plan",
  "Resume music when browsing Steam while a game or app is still running. Stops when you return to the game.":
    "Reprend la musique pendant la navigation dans Steam lorsqu’un jeu ou une application tourne encore. S’arrête au retour au jeu.",
  "Enable global/ambient track": "Activer la piste globale/ambiante",
  "Keep global track assigned, but toggle its playback on non-game pages.":
    "Conserve la piste globale assignée, mais active ou désactive sa lecture hors des pages de jeu.",
  "Enable store track": "Activer la piste de la boutique",
  "Keep store track assigned, but toggle its playback on store pages.":
    "Conserve la piste de la boutique assignée, mais active ou désactive sa lecture sur les pages de la boutique.",
  "Disable global/ambient track while in game store":
    "Désactiver la piste globale/ambiante dans la boutique",
  "When enabled, global ambient music is muted on store pages.":
    "Lorsque cette option est activée, la musique ambiante globale est coupée sur les pages de la boutique.",
  "Global/ambient interruption behavior":
    "Comportement en cas d’interruption de la piste globale/ambiante",
  "When game/store music interrupts global ambient:":
    "Lorsque la musique d’un jeu ou de la boutique interrompt la musique ambiante globale\u00A0:",
  "Global ambient interruption behavior":
    "Comportement en cas d’interruption de la musique ambiante globale",
  "Stop (restart)": "Arrêter (redémarrer)",
  "Choose global/ambient track...": "Choisir la piste globale/ambiante…",
  "Choose store-only track...": "Choisir la piste de la boutique…",
  "Use Firefox cookies for YouTube": "Utiliser les cookies Firefox pour YouTube",
  "Enable only when YouTube asks you to sign in or confirm you are not a bot. Firefox must be signed into YouTube.":
    "N’activez cette option que si YouTube vous demande de vous connecter ou de confirmer que vous n’êtes pas un robot. Firefox doit être connecté à YouTube.",
  "Use this if YouTube search, previews, or downloads stop working.":
    "Utilisez cette option si la recherche, les aperçus ou les téléchargements YouTube cessent de fonctionner.",
  "Song storage": "Stockage des morceaux",
  "Manage downloaded songs and preview cache":
    "Gérez les morceaux téléchargés et le cache des aperçus",
  "Auto-assign missing game tracks (yt-dlp)":
    "Assigner automatiquement les pistes manquantes (yt-dlp)",
  "Uses first YouTube result per game and only targets games with no assigned track.":
    "Utilise le premier résultat YouTube de chaque jeu et ne cible que les jeux sans piste assignée.",
  "Games currently without music assigned: {count}":
    "Jeux sans musique assignée actuellement\u00A0: {count}",
  "Total library games detected: {count}":
    "Jeux détectés dans la bibliothèque\u00A0: {count}",
  "Download music for all games": "Télécharger la musique pour tous les jeux",
  "Download music only for installed games":
    "Télécharger la musique pour les jeux installés uniquement",
  "Download music only for uninstalled games":
    "Télécharger la musique pour les jeux non installés uniquement",
  "STOP": "ARRÊTER",
  "{completed}/{total} completed • assigned {assigned}":
    "{completed}/{total} terminés • {assigned} assignés",
  "skipped {skipped} • failed {failed}": "ignorés\u00A0: {skipped} • échoués\u00A0: {failed}",
  "Current game:": "Jeu en cours\u00A0:",
  "{resolved}/{total} names resolved • pending {pending} • unavailable {unavailable}":
    "{resolved}/{total} noms résolus • {pending} en attente • {unavailable} indisponibles",
  "• checking {count}": "• vérification de {count}",
  "Resolving game names...": "Résolution des noms de jeux…",
  "No games are missing music.": "Aucun jeu ne manque de musique.",
  "No games found in library.": "Aucun jeu trouvé dans la bibliothèque.",
  "Global / ambient track": "Piste globale / ambiante",
  "No global track selected.": "Aucune piste globale sélectionnée.",
  "Remove global ambient music": "Retirer la musique ambiante globale",
  "Volume": "Volume",
  "Start skip": "Ignorer le début",
  "Loop track": "Lire la piste en boucle",
  "Play continuously when this track is active.":
    "Lecture continue tant que cette piste est active.",
  "Store-only track": "Piste de la boutique",
  "No store-only track selected.": "Aucune piste de la boutique sélectionnée.",
  "Remove store-only music": "Retirer la musique de la boutique",
  "ThemeDeck master volume": "Volume principal ThemeDeck",
  "Master volume override": "Forcer le volume principal",
  "At 100%, ThemeDeck respects each game/global/store track volume. Below 100%, all ThemeDeck music plays at this volume instead.":
    "À 100\u00A0%, ThemeDeck respecte le volume de chaque piste (jeu, globale, boutique). En dessous de 100\u00A0%, toute la musique ThemeDeck est lue à ce volume.",

  // --- Notifications and errors --------------------------------------------
  "Unable to resume music": "Impossible de reprendre la musique",
  "Couldn't determine current game app id":
    "Impossible de déterminer l’identifiant du jeu en cours",
  "Unable to reorder songs": "Impossible de réorganiser les morceaux",
  "Unable to remove song": "Impossible de retirer le morceau",
  "Failed to load saved tracks": "Impossible de charger les pistes enregistrées",
  "Unknown library scan error": "Erreur inconnue lors de l’analyse de la bibliothèque",
  "Unknown settings error": "Erreur inconnue des paramètres",
  "Unknown update error": "Erreur de mise à jour inconnue",
  "Unknown search error": "Erreur de recherche inconnue",
  "Unknown download error": "Erreur de téléchargement inconnue",
  "Updating YouTube support (yt-dlp and Deno). This can take a minute.":
    "Mise à jour de la prise en charge de YouTube (yt-dlp et Deno). Cela peut prendre une minute.",
  "Stopping after current operation...": "Arrêt après l’opération en cours…",
  "YouTube support is not ready. Use Update YouTube support first.":
    "La prise en charge de YouTube n’est pas prête. Utilisez d’abord «\u00A0Mettre à jour la prise en charge de YouTube\u00A0».",
  "Couldn't save global track volume":
    "Impossible d’enregistrer le volume de la piste globale",
  "Couldn't save global song start truncation":
    "Impossible d’enregistrer le début ignoré de la piste globale",
  "Couldn't save global track loop setting":
    "Impossible d’enregistrer la lecture en boucle de la piste globale",
  "Failed to remove global track": "Impossible de retirer la piste globale",
  "Couldn't save store track volume":
    "Impossible d’enregistrer le volume de la piste de la boutique",
  "Couldn't save store song start truncation":
    "Impossible d’enregistrer le début ignoré de la piste de la boutique",
  "Couldn't save store track loop setting":
    "Impossible d’enregistrer la lecture en boucle de la piste de la boutique",
  "Failed to remove store track": "Impossible de retirer la piste de la boutique",
  "Failed to read yt-dlp status": "Impossible de lire l’état de yt-dlp",
  "Enter a search query first": "Saisissez d’abord une recherche",
  "Preview failed": "Échec de l’aperçu",
  "Couldn't save volume": "Impossible d’enregistrer le volume",
  "Couldn't save song start truncation":
    "Impossible d’enregistrer le début ignoré du morceau",
  "Couldn't save loop setting": "Impossible d’enregistrer la lecture en boucle",

  "Can't play {file}: {error}": "Impossible de lire {file}\u00A0: {error}",
  "Unknown playback error": "Erreur de lecture inconnue",
  "Failed to save Firefox cookie setting: {error}":
    "Impossible d’enregistrer le réglage des cookies Firefox\u00A0: {error}",
  "Failed to update YouTube support: {error}":
    "Impossible de mettre à jour la prise en charge de YouTube\u00A0: {error}",
  "Failed to install YouTube support: {error}":
    "Impossible d’installer la prise en charge de YouTube\u00A0: {error}",
  "YouTube support ready (yt-dlp {version}, Deno {deno})":
    "Prise en charge de YouTube prête (yt-dlp {version}, Deno {deno})",
  "ready": "prêt",
  "latest": "à jour",
  "Added track for {name}. Existing songs kept.":
    "Piste ajoutée pour {name}. Les morceaux existants sont conservés.",
  "Added \"{file}\" for {name}. Existing songs kept.":
    "«\u00A0{file}\u00A0» ajouté pour {name}. Les morceaux existants sont conservés.",
  "Unable to add file ({path}): {error}":
    "Impossible d’ajouter le fichier ({path})\u00A0: {error}",
  "Unable to add that file": "Impossible d’ajouter ce fichier",
  "YouTube search failed: {error}": "La recherche YouTube a échoué\u00A0: {error}",
  "Preview failed: {error}": "Échec de l’aperçu\u00A0: {error}",
  "Download failed: {error}": "Échec du téléchargement\u00A0: {error}",
  "YouTube download failed: {error}":
    "Le téléchargement YouTube a échoué\u00A0: {error}",
  "Unassigned music for {name}. File kept; use Manage storage to delete downloads.":
    "Musique désassignée pour {name}. Le fichier est conservé\u00A0; utilisez la gestion du stockage pour supprimer les téléchargements.",

  // --- Bulk assignment progress --------------------------------------------
  "Assigned songs ({count})": "Morceaux assignés ({count})",
  "Preparing bulk assignment...": "Préparation de l’assignation automatique…",
  "Preparing bulk assignment... ({count} unnamed games will still be attempted)":
    "Préparation de l’assignation automatique… ({count} jeux sans nom seront tout de même tentés)",
  "Skipped {game} (already assigned).": "Ignoré\u00A0: {game} (déjà assigné).",
  "Searching YouTube for {game} ({query})...":
    "Recherche YouTube pour {game} ({query})…",
  "Search failed for {game}: {error}":
    "Échec de la recherche pour {game}\u00A0: {error}",
  "No eligible YouTube results for {game}.":
    "Aucun résultat YouTube exploitable pour {game}.",
  "Downloading match {index}/{total} for {game}...":
    "Téléchargement du résultat {index}/{total} pour {game}…",
  "Assigned {game}.": "{game} assigné.",
  "All download attempts failed for {game}: {error}":
    "Toutes les tentatives de téléchargement ont échoué pour {game}\u00A0: {error}",
  "No usable results": "Aucun résultat exploitable",
  "Stopped. Assigned {assigned}, skipped {skipped}, failed {failed}.":
    "Opération arrêtée. {assigned} assignés, {skipped} ignorés, {failed} échoués.",
  "Done. Assigned {assigned}, skipped {skipped}, failed {failed}.":
    "Terminé. {assigned} assignés, {skipped} ignorés, {failed} échoués.",
  "Bulk assign stopped. Assigned {assigned}, skipped {skipped}, failed {failed}.":
    "Assignation automatique arrêtée. {assigned} assignés, {skipped} ignorés, {failed} échoués.",
  "Bulk assign complete. Assigned {assigned}, skipped {skipped}, failed {failed}.":
    "Assignation automatique terminée. {assigned} assignés, {skipped} ignorés, {failed} échoués.",
  "No installed games are missing assigned music.":
    "Aucun jeu installé ne manque de musique assignée.",
  "No uninstalled games are missing assigned music.":
    "Aucun jeu non installé ne manque de musique assignée.",
  "No library games are missing assigned music.":
    "Aucun jeu de la bibliothèque ne manque de musique assignée.",
  "(stopping...)": "(arrêt en cours…)",

  // --- Game page music picker ----------------------------------------------
  "Invalid game id.": "Identifiant de jeu invalide.",
  "Music for {name}": "Musique pour {name}",
  "Search YouTube • Add music": "Rechercher sur YouTube • Ajouter de la musique",
  "Search YouTube for game music, download audio locally, and assign it to this game. Enable Firefox cookies below if YouTube asks you to sign in.":
    "Recherchez la musique d’un jeu sur YouTube, téléchargez l’audio en local et assignez-le à ce jeu. Activez les cookies Firefox ci-dessous si YouTube vous demande de vous connecter.",
  "Installing/updating yt-dlp and Deno. This can take a minute.":
    "Installation/mise à jour de yt-dlp et Deno. Cela peut prendre une minute.",
  "Firefox must be installed and signed into YouTube. Leave this disabled unless YouTube requires authentication.":
    "Firefox doit être installé et connecté à YouTube. Laissez cette option désactivée, sauf si YouTube exige une authentification.",
  "Selected": "Sélectionné",
  "Currently assigned": "Assigné actuellement",
  "No results yet. Search for a game soundtrack above.":
    "Aucun résultat pour l’instant. Recherchez la bande originale d’un jeu ci-dessus.",
  "Playlist settings": "Réglages de la playlist",
  "Hide playlist settings": "Masquer les réglages de la playlist",
  "Loop playlist": "Lire la playlist en boucle",
  "Unassign all songs": "Retirer tous les morceaux",
  "No music selected yet.": "Aucune musique sélectionnée.",
  "Local audio files": "Fichiers audio locaux",
  "Browse local files": "Parcourir les fichiers locaux",
  "Hide local files": "Masquer les fichiers locaux",
  "Hide song storage": "Masquer le stockage des morceaux",
  "No folders or audio files here.": "Aucun dossier ni fichier audio ici.",
  "Add: {file}": "Ajouter\u00A0: {file}",
  "Assign: {file}": "Assigner\u00A0: {file}",
  "New songs are added to this playlist. Use the arrows to change playback order.":
    "Les nouveaux morceaux sont ajoutés à cette playlist. Utilisez les flèches pour modifier l’ordre de lecture.",
  "No songs yet. Search YouTube to add your first song.":
    "Aucun morceau pour l’instant. Recherchez sur YouTube pour ajouter votre premier morceau.",
  "Move up": "Déplacer vers le haut",
  "Move down": "Déplacer vers le bas",
  "yt-dlp not installed": "yt-dlp non installé",
  "Deno not configured": "Deno non configuré",
  "Update YouTube support": "Mettre à jour la prise en charge de YouTube",
  "Hide games without music": "Masquer les jeux sans musique",
  "Show games without music": "Afficher les jeux sans musique",
  "Pause preview": "Mettre l’aperçu en pause",
  "Preview track": "Écouter la piste",
  "Download & Add keeps your existing songs.":
    "Télécharger et ajouter conserve vos morceaux existants.",
  "Find a soundtrack, preview it, then download.":
    "Trouvez une bande originale, écoutez-la, puis téléchargez-la.",
  "Hide setup": "Masquer la configuration",
  "YouTube setup": "Configuration YouTube",
  "Set up YouTube support": "Configurer la prise en charge de YouTube",
  "Install YouTube support": "Installer la prise en charge de YouTube",
  "Search YouTube": "Rechercher sur YouTube",
  "Stop Preview": "Arrêter l’aperçu",
  "Play Preview": "Lire l’aperçu",

  // --- File browser ---------------------------------------------------------
  "Home": "Accueil",
  "Music": "Musique",
  "Downloads": "Téléchargements",
  "SD card": "Carte SD",
  "Root": "Racine",

  // --- Song storage panel ---------------------------------------------------
  "Unable to read song storage": "Impossible de lire le stockage des morceaux",
  "Unable to delete files": "Impossible de supprimer les fichiers",
  "Unable to delete downloaded song":
    "Impossible de supprimer le morceau téléchargé",
  "Global ambient": "Ambiante globale",
  "Store": "Boutique",
  "Game {id}": "Jeu {id}",
  "Manage songs downloaded by ThemeDeck and cached YouTube previews. Your own music outside these folders is not listed or deleted.":
    "Gérez les morceaux téléchargés par ThemeDeck et les aperçus YouTube mis en cache. Votre propre musique en dehors de ces dossiers n’est ni listée ni supprimée.",
  "Deleting a file permanently removes it and clears all its assignments. Your own music outside ThemeDeck folders is excluded.":
    "Supprimer un fichier le retire définitivement et efface toutes ses assignations. Votre propre musique en dehors des dossiers ThemeDeck est exclue.",
  "Total:": "Total\u00A0:",
  "Downloads: {size}": "Téléchargements\u00A0: {size}",
  "Previews: {size}": "Aperçus\u00A0: {size}",
  "Unused: {size}": "Inutilisés\u00A0: {size}",
  "A preview or download is in progress. Deletion is paused; refresh after it finishes.":
    "Un aperçu ou un téléchargement est en cours. La suppression est suspendue\u00A0; actualisez une fois l’opération terminée.",
  "Refresh storage": "Actualiser le stockage",
  "Clear cached previews": "Vider le cache des aperçus",
  "Delete all unused files": "Supprimer tous les fichiers inutilisés",
  "Clear missing-file assignments ({count})":
    "Effacer les assignations orphelines ({count})",
  "Working…": "En cours…",
  "Confirm clear assignments": "Confirmer l’effacement des assignations",
  "Confirm permanent deletion": "Confirmer la suppression définitive",
  "Files — largest first": "Fichiers — les plus volumineux d’abord",
  "All": "Tous",
  "Previews": "Aperçus",
  "Unused": "Inutilisés",
  "No files in this category.": "Aucun fichier dans cette catégorie.",
  "Preview cache": "Cache des aperçus",
  "Assigned to: {assignments}": "Assigné à\u00A0: {assignments}",
  "Unused — no assignments": "Inutilisé — aucune assignation",
  "Delete from disk…": "Supprimer du disque…",
  "Show more files ({count} remaining)":
    "Afficher plus de fichiers ({count} restants)",
  "Missing-file assignments cleared. No files were deleted.":
    "Les assignations orphelines ont été effacées. Aucun fichier n’a été supprimé.",
  "Freed {size}.": "{size} libérés.",
  "Some files could not be deleted: {errors}":
    "Certains fichiers n’ont pas pu être supprimés\u00A0: {errors}",
  "Delete all unused cached previews? Assigned files will be kept. You can download previews again.":
    "Supprimer tous les aperçus mis en cache et inutilisés\u00A0? Les fichiers assignés seront conservés. Vous pourrez télécharger à nouveau des aperçus.",
  "Permanently delete all unassigned ThemeDeck downloads and previews? Assigned songs and your own local music will be kept.":
    "Supprimer définitivement tous les téléchargements et aperçus ThemeDeck non assignés\u00A0? Les morceaux assignés et votre musique locale seront conservés.",
  "Clear {count} assignments whose files are missing? This removes broken references without deleting any files.":
    "Effacer {count} assignations dont les fichiers sont introuvables\u00A0? Cela supprime les références cassées sans supprimer aucun fichier.",
  "Permanently delete “{name}” ({size})? {assignments}":
    "Supprimer définitivement «\u00A0{name}\u00A0» ({size})\u00A0? {assignments}",
  "This will also clear: {assignments}.":
    "Cela effacera aussi\u00A0: {assignments}.",
  "This file has no assignments.": "Ce fichier n’a aucune assignation.",
  "Permanently delete “{name}” ({size}) from disk? This also clears: {assignments}. This cannot be undone.":
    "Supprimer définitivement «\u00A0{name}\u00A0» ({size}) du disque\u00A0? Cela effacera aussi\u00A0: {assignments}. Cette action est irréversible.",
  "Deleting…": "Suppression…",
  "Delete downloaded file from disk…": "Supprimer le fichier téléchargé du disque…",
};

package com.calorieai.app.ui.add

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import com.calorieai.app.R
import com.calorieai.app.ui.components.ShimmerLoading
import com.calorieai.app.util.CameraFileProvider

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddScreen(
    onSavedNavigateToDiary: () -> Unit,
    viewModel: AddViewModel = hiltViewModel()
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val snackbarHostState = remember { SnackbarHostState() }

    val savedMessage = stringResource(R.string.add_saved)
    val cameraDeniedMessage = stringResource(R.string.permission_camera_denied)

    // Показ помилок аналізу.
    state.errorRes?.let { res ->
        val message = stringResource(res)
        LaunchedEffect(res, message) {
            snackbarHostState.showSnackbar(message)
            viewModel.errorShown()
        }
    }

    // Подія успішного збереження -> snackbar + перехід у щоденник.
    LaunchedEffect(state.savedEvent) {
        if (state.savedEvent) {
            snackbarHostState.showSnackbar(savedMessage)
            viewModel.savedEventHandled()
            onSavedNavigateToDiary()
        }
    }

    // --- Лаунчери камери та галереї ---
    var pendingCameraUri by remember { mutableStateOf<Uri?>(null) }

    val takePictureLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success ->
        if (success) pendingCameraUri?.let { viewModel.onPhotoCaptured(it) }
    }

    val pickMediaLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia()
    ) { uri -> uri?.let { viewModel.onPhotoCaptured(it) } }

    val launchCamera = {
        val uri = CameraFileProvider.createImageUri(context)
        pendingCameraUri = uri
        takePictureLauncher.launch(uri)
    }

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            launchCamera()
        }
    }

    val onTakePhoto = {
        val granted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) launchCamera() else cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text(stringResource(R.string.add_title)) }) },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            TabRow(selectedTabIndex = state.tab.ordinal) {
                Tab(
                    selected = state.tab == AddTab.TEXT,
                    onClick = { viewModel.selectTab(AddTab.TEXT) },
                    text = { Text(stringResource(R.string.add_tab_text)) }
                )
                Tab(
                    selected = state.tab == AddTab.PHOTO,
                    onClick = { viewModel.selectTab(AddTab.PHOTO) },
                    text = { Text(stringResource(R.string.add_tab_photo)) }
                )
            }

            when (state.tab) {
                AddTab.TEXT -> TextInputSection(
                    text = state.textInput,
                    enabled = !state.isLoading,
                    onTextChange = viewModel::onTextChange,
                    onAnalyze = viewModel::analyzeText
                )
                AddTab.PHOTO -> PhotoInputSection(
                    photoUri = state.photoUri,
                    enabled = !state.isLoading,
                    onTakePhoto = onTakePhoto,
                    onPickGallery = {
                        pickMediaLauncher.launch(
                            PickVisualMediaRequest(
                                ActivityResultContracts.PickVisualMedia.ImageOnly
                            )
                        )
                    }
                )
            }

            AnimatedVisibility(visible = state.isLoading) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        text = stringResource(R.string.add_analyzing),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.primary
                    )
                    ShimmerLoading()
                }
            }

            AnimatedVisibility(visible = state.hasResults && !state.isLoading) {
                ResultsSection(
                    state = state,
                    onEdit = viewModel::updateResult,
                    onRemove = viewModel::removeResult,
                    onSaveAll = viewModel::saveAll,
                    onClear = viewModel::clearResults
                )
            }
        }
    }
}

@Composable
private fun TextInputSection(
    text: String,
    enabled: Boolean,
    onTextChange: (String) -> Unit,
    onAnalyze: () -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedTextField(
            value = text,
            onValueChange = onTextChange,
            label = { Text(stringResource(R.string.add_tab_text)) },
            placeholder = { Text(stringResource(R.string.add_text_hint)) },
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 140.dp),
            enabled = enabled
        )
        Button(
            onClick = onAnalyze,
            enabled = enabled,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 52.dp)
        ) {
            Icon(Icons.Filled.AutoAwesome, contentDescription = null)
            Text(
                text = "  ${stringResource(R.string.add_analyze)}",
                style = MaterialTheme.typography.titleMedium
            )
        }
    }
}

@Composable
private fun PhotoInputSection(
    photoUri: Uri?,
    enabled: Boolean,
    onTakePhoto: () -> Unit,
    onPickGallery: () -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (photoUri != null) {
            AsyncImage(
                model = photoUri,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(4f / 3f)
                    .clip(RoundedCornerShape(20.dp))
            )
        } else {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(4f / 3f)
                    .clip(RoundedCornerShape(20.dp))
                    .padding(16.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = stringResource(R.string.add_photo_placeholder),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = onTakePhoto,
                enabled = enabled,
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 52.dp)
            ) {
                Icon(Icons.Filled.PhotoCamera, contentDescription = null)
                Text("  ${stringResource(R.string.add_take_photo)}")
            }
            OutlinedButton(
                onClick = onPickGallery,
                enabled = enabled,
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 52.dp)
            ) {
                Icon(Icons.Filled.PhotoLibrary, contentDescription = null)
                Text("  ${stringResource(R.string.add_pick_gallery)}")
            }
        }
    }
}
